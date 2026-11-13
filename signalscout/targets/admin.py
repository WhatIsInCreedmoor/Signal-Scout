from django.contrib import admin
from .models import Target, Watcher, TrackedTarget, DeviceMAC, DeploymentLocation, FalsePositiveFilter, Definition, DefinitionOUI, DefinitionName, FirmwareRelease, FirmwareBinary

class DeviceMACInline(admin.TabularInline):
    model = DeviceMAC
    extra = 1

@admin.register(TrackedTarget)
class TrackedTargetAdmin(admin.ModelAdmin):
    ordering = ('alias',)
    list_display = ('alias', 'car_number', 'license_plate', 'operator')
    search_fields = ('alias', 'car_number', 'license_plate', 'operator', 'macs__mac_address', 'macs__description', 'notes')
    list_filter = ('is_active', 'operator')
    inlines = [DeviceMACInline]

@admin.register(Target)
class TargetAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'mac_address', 'tracked_target', 'operator', 'channel', 'device_name', 'area', 'uploaded_by__mac_address')
    search_fields = ('mac_address', 'operator', 'network_type', 'device_name', 'area', 'uploaded_by__mac_address')

@admin.register(Watcher)
class WatcherAdmin(admin.ModelAdmin):
    list_display = ('mac_address', 'device_type', 'deployment_location', 'firmware_version', "notes", 'is_active', 'auto_update_enabled', 'last_uploaded', 'last_seen')
    search_fields = ('mac_address', 'device_type', 'deployment_location', 'is_active', 'last_seen', 'firmware_version')
    ordering = ('-is_active', '-last_seen')

@admin.register(DeploymentLocation)
class DeploymentLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'latitude', 'longitude')
    search_fields = ('name', 'notes')

@admin.register(FalsePositiveFilter)
class FalsePositiveFilterAdmin(admin.ModelAdmin):
    list_display = ('name', 'notes', 'mac_address', 'mac_oui', 'device_name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'mac_address', 'mac_oui', 'device_name', "notes")

class DefinitionOUIInline(admin.TabularInline):
    model = DefinitionOUI
    extra = 1

class DefinitionNameInline(admin.TabularInline):
    model = DefinitionName
    extra = 1

@admin.register(Definition)
class DefinitionAdmin(admin.ModelAdmin):
    list_display = ('definition_name', 'definition_type', 'operator', 'confidence', 'is_active', 'notes')
    list_filter = ('definition_type', 'confidence', 'operator', 'is_active')
    search_fields = ('definition_name', 'names__device_name', 'ouis__oui', 'operator', 'notes')
    list_editable = ('definition_type', 'is_active', 'confidence')
    ordering = ('-definition_type', 'definition_name')
    inlines = [DefinitionOUIInline, DefinitionNameInline]

class FirmwareBinaryInline(admin.TabularInline):
    model = FirmwareBinary
    extra = 1

@admin.register(FirmwareRelease)
class FirmwareReleaseAdmin(admin.ModelAdmin):
    list_display = ('version', 'get_hardware_targets', 'release_date', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('version',)
    inlines = [FirmwareBinaryInline]

    def get_hardware_targets(self, obj):
        # Grabs all child binaries and joins their names (e.g., "esp32c6, esp32c3")
        targets = [b.get_hardware_target_display() for b in obj.binaries.all()]
        return ", ".join(targets) if targets else "None"

    get_hardware_targets.short_description = 'Available Targets'
