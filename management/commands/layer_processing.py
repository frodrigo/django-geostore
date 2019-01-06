from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils.module_loading import import_string

from terracommon.terra import GIS_LINESTRING, GIS_POINT, GIS_POLYGON
from terracommon.terra.models import Feature, Layer


class Command(BaseCommand):
    help = 'Run a data processing on layers - UNSAFE command'

    def add_arguments(self, parser):
        parser.add_argument(
            '-pk-ins', '--layer-pk-ins',
            default=[],
            required=True,
            action='append',
            help=("PKs of the input layers."))
        parser.add_argument(
            '-pk-out', '--layer-pk-out',
            type=int,
            action="store",
            help=("PK of the output layer."))
        parser.add_argument(
            '-co', '--clear_output',
            action="store_true",
            help=("Empty the output layer before adding data."))
        exclusive_group = parser.add_mutually_exclusive_group()
        exclusive_group.add_argument(
            '-s', '--sql',
            action="store",
            help=("UNSAFE SQL Query. Eg. SELECT identifier, properties, ST_Centroid(geom::geometry) AS geom FROM in0"))
        exclusive_group.add_argument(
            '-s-centroid', '--sql-centroid',
            action="store_true",
            help=("Compute centroid"))
        exclusive_group.add_argument(
            '-p', '--python',
            help=("UNSAFE Compute with a python callable module, use multiple key=value as arguments"))
        exclusive_group.add_argument(
            '-mv', '--make-valid',
            action="store_true",
            help=("Enforce valide geomtries"))
        parser.add_argument(
            '--dry-run',
            action="store_true",
            help='Execute une dry-run mode')
        parser.add_argument(
            'command_args',
            nargs='*',
            action="store",
            help='Processing command arguments')

    def _get_layer_ins(self, layer_pk_ins):
        try:
            return [Layer.objects.get(pk=layer_pk_in) for layer_pk_in in layer_pk_ins]
        except ObjectDoesNotExist:
            raise CommandError(f"Fails open one or many layers layer-pk-ins: {', '.join(layer_pk_ins)}")

    def _get_layer_out(self, layer_pk_out, clear_output, verbosity):
        if layer_pk_out:
            try:
                layer_out = Layer.objects.get(pk=layer_pk_out)
            except ObjectDoesNotExist:
                raise CommandError(f'Fails open layers layer-pk-out: {layer_pk_out}')
            if clear_output:
                layer_out.features.all().delete()
        else:
            layer_out = Layer.objects.create()
            if verbosity >= 1:
                self.stdout.write(
                    f"The created layer pk is {layer_out.pk}, "
                    "it can be used to import more features "
                    "in the same layer with different "
                    "options")

        return layer_out

    @transaction.atomic()
    def handle(self, *args, **options):
        dryrun = options.get('dry_run')
        sp = transaction.savepoint()
        layer_ins = self._get_layer_ins(options.get('layer_pk_ins'))
        layer_out = self._get_layer_out(options.get('layer_pk_out'), options.get('clear_output'), options['verbosity'])
        command_args = dict([a.split('=', 1) for a in options.get('command_args') or []])

        sql = options.get('sql')
        python_object_name = options.get('python')

        if python_object_name:
            self._call(python_object_name, layer_ins, layer_out, **command_args)
        elif options.get('sql_centroid'):
            self._simple_sql('ST_Centroid', layer_ins, layer_out)
        elif options.get('sql_make_valid'):
            self._simple_sql('ST_MakeValid', layer_ins, layer_out)
        elif sql:
            self._sql(sql, layer_ins, layer_out)
        elif options.get('make_valid'):
            self._processing_make_valid(layer_ins, layer_out)
        else:
            raise CommandError("Missing processing SQL or pyhton")

        if dryrun:
            transaction.savepoint_rollback(sp)
        else:
            transaction.savepoint_commit(sp)

    def _call(self, python_callable_name, layer_ins, layer_out, **command_args):
        callable_object = import_string(python_callable_name)
        callable_object(layer_ins, layer_out, **command_args)

    def _simple_sql(self, sql_function, layer_ins, layer_out):
        return self._sql(
            f'SELECT identifier, properties, {sql_function}(geom::geometry) AS geom FROM in0',
            layer_ins, layer_out)

    def _sql(self, sql, layer_ins, layer_out):
        args = []
        raws = []
        for (i, l) in enumerate(layer_ins):
            raw, arg = l.features.all().query.sql_with_params()
            raws.append(f'in{i} AS ({raw})')
            args.append(arg)
        with_ = ',\n'.join(raws)

        with connection.cursor() as cursor:
            sql_query = f'''
                WITH
                {with_}
                INSERT INTO {Feature._meta.db_table} (layer_id, identifier, properties, geom)
                SELECT {layer_out.id}, * FROM (
                    {sql}
                ) AS t
            '''
            self.stdout.write(sql_query)

            cursor.execute(sql_query, args)

    def _processing_make_valid(self, layer_ins, layer_out):
        if len(layer_ins) != 1:
            raise ValueError('Exactly one input layer required')
        layer_in = layer_ins[0]

        if layer_in.layer_geometry in GIS_POINT:
            raise NotImplementedError
        elif layer_in.layer_geometry in GIS_LINESTRING:
            raise NotImplementedError
        elif layer_in.layer_geometry in GIS_POLYGON:
            if not layer_in.layer_geometry.startswith('Multi'):
                # Polygon
                self._sql(
                    """
                    SELECT
                        identifier,
                        properties,
                        CASE
                            WHEN (
                                SELECT geom
                                FROM ST_Dump(ST_CollectionExtract(ST_MakeValid(geom::geometry), 3))
                                LIMIT 1
                            ) IS NOT NULL
                                THEN (
                                    SELECT geom
                                    FROM ST_Dump(ST_CollectionExtract(ST_MakeValid(geom::geometry), 3))
                                    LIMIT 1
                                )
                            ELSE ST_BUFFER(geom::geometry, 0)
                        END
                    FROM
                        in0
                    """,
                    layer_ins, layer_out)
            else:
                # MultiPolygon
                self._sql(
                    """
                    SELECT
                        identifier,
                        properties,
                        CASE
                            WHEN ST_CollectionExtract(ST_MakeValid(geom::geometry), 3) IS NOT NULL
                                THEN ST_CollectionExtract(ST_MakeValid(geom::geometry), 3)
                            ELSE ST_BUFFER(geom::geometry, 0)
                        END
                    FROM
                        in0
                    """,
                    layer_ins, layer_out)