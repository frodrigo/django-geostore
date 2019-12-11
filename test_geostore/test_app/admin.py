from django.contrib import admin
from geostore import models
from django.contrib.gis.admin import OSMGeoAdmin


class ArrayObjectPropertyAdminInline(admin.TabularInline):
    model = models.ArrayObjectProperty


class LayerSchemaPropertyAdminInline(admin.TabularInline):
    model = models.LayerSchemaProperty


class LayerExtraGeomInline(admin.TabularInline):
    model = models.LayerExtraGeom


class FeatureExtraGeomInline(admin.TabularInline):
    model = models.FeatureExtraGeom


class LayerSchemaPropertyAdmin(admin.ModelAdmin):
    inlines = [ArrayObjectPropertyAdminInline, ]


@admin.register(models.Layer)
class LayerAdmin(admin.ModelAdmin):
    inlines = [LayerExtraGeomInline, LayerSchemaPropertyAdminInline]


@admin.register(models.Feature)
class FeatureAdmin(OSMGeoAdmin):
    inlines = [FeatureExtraGeomInline]


admin.site.register(models.ArrayObjectProperty)
admin.site.register(models.LayerSchemaProperty, LayerSchemaPropertyAdmin)
