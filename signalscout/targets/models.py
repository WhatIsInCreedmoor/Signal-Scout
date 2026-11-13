import secrets
from django.db import models
import os


def generate_auth_key():
    return secrets.token_hex(32)

class FalsePositiveFilter(models.Model):
    name = models.CharField(max_length=128, blank=True, null=True, help_text="Rule name (e.g., 'Ubiquiti OUI' or 'Public Wi-Fi')")
    mac_address = models.CharField(max_length=17, blank=True, null=True, help_text="Exact match (e.g., '00:11:22:33:44:55')")
    mac_oui = models.CharField(max_length=8, blank=True, null=True, help_text="Starts with match (e.g., '78:45:58')")
    device_name = models.CharField(max_length=255, blank=True, null=True, help_text="Substring match for SSID or Bluetooth name (e.g., 'access point')")
    notes = models.TextField(blank=True, null=True, help_text="Internal notes or reasons for this filter")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        if self.name:
            return self.name
        # Fallback names for the admin panel if 'name' is left blank
        if self.mac_address:
            return f"Filter MAC: {self.mac_address}"
        if self.mac_oui:
            return f"Filter OUI: {self.mac_oui}"
        if self.device_name:
            return f"Filter Name: {self.device_name}"
        return "Unnamed Filter"

class TrackedTarget(models.Model):
    alias = models.CharField(max_length=64, blank=True, null=True, help_text="Friendly name (e.g., 'PD: Car 105')")
    operator = models.CharField(max_length=64, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    license_plate = models.CharField(max_length=15, blank=True, null=True)
    car_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return self.alias or f"Unknown Target #{self.id}"

class DeviceMAC(models.Model):
    tracked_target = models.ForeignKey(TrackedTarget, on_delete=models.CASCADE, related_name='macs')
    mac_address = models.CharField(max_length=17)
    description = models.CharField(max_length=64, blank=True, help_text="e.g., 'CradlePoint 5G' or 'Axon Bodycam'")

    def __str__(self):
        return f"{self.mac_address} ({self.tracked_target.alias})"

class Watcher(models.Model):
    mac_address = models.CharField(max_length=17, unique=True, null=True, blank=True)
    device_type = models.CharField(max_length=100, help_text="e.g., Seeed XIAO ESP32C6",  default="Seeed XIAO ESP32")
    deployment_location = models.ForeignKey('DeploymentLocation', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_uploaded = models.DateTimeField(null=True, blank=True)
    auth_key = models.CharField(max_length=64, unique=True, default=generate_auth_key)
    firmware_version = models.CharField(max_length=32, default="1.0.0")
    auto_update_enabled = models.BooleanField(default=False, help_text="Allow OTA updates")
    hardware_target = models.CharField(max_length=32, blank=True, null=True, help_text="Auto-populated by the device (e.g., esp32c6)")

    def __str__(self):
        return f"{self.mac_address} - {self.device_type}"

class Target(models.Model):
    tracked_target = models.ForeignKey(
        TrackedTarget,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='detections'
    )
    NETWORK_CHOICES = [
        ('WIFI', 'WiFi'),
        ('BT', 'Bluetooth'),
    ]
    CONFIDENCE_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    operator = models.CharField(max_length=255, null=True, blank=True)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, null=True, blank=True)
    timestamp = models.DateTimeField()
    mac_address = models.CharField(max_length=17)
    network_type = models.CharField(max_length=4, choices=NETWORK_CHOICES)
    channel = models.IntegerField(null=True, blank=True)
    signal_strength = models.IntegerField(null=True, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    device_name = models.CharField(max_length=255, null=True, blank=True)
    manufacturer = models.CharField(max_length=255, null=True, blank=True)
    user_description = models.TextField(null=True, blank=True)
    area = models.CharField(max_length=255, null=True, blank=True, help_text="e.g., Area: XX Neighborhood")
    uploaded_by = models.ForeignKey(Watcher, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.mac_address} - {self.network_type}"

class DeploymentLocation(models.Model):
    name = models.CharField(max_length=128, unique=True, help_text="Name of the deployment location")
    latitude = models.FloatField()
    longitude = models.FloatField()
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Definition(models.Model):
    INCLUDE = 'include'
    EXCLUDE = 'exclude'
    TYPE_CHOICES = [
        (INCLUDE, 'Include'),
        (EXCLUDE, 'Exclude'),
    ]

    CONFIDENCE_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    definition_name = models.CharField(max_length=128, blank=True, null=True, help_text="Friendly name for this rule (e.g., 'Axon Bodycams')")
    definition_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=INCLUDE)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default='medium')
    operator = models.CharField(max_length=255, blank=True, null=True, help_text="e.g., County Sheriff. Local PD")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True, help_text="Details of definition.")

    def __str__(self):
        if self.definition_name:
            return self.definition_name
        return f"{self.definition_type.title()} Rule #{self.id}"


class DefinitionOUI(models.Model):
    definition = models.ForeignKey(Definition, on_delete=models.CASCADE, related_name='ouis')
    oui = models.CharField(max_length=8, help_text="Format: XX:XX:XX")
    vmac_expansion = models.BooleanField(default=False, help_text="Automatically track locally administered virtual MACs (BSSIDs).")

    def save(self, *args, **kwargs):
        if self.oui:
            self.oui = self.oui.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.oui} ({self.definition.definition_name or 'Rule'})"


class DefinitionName(models.Model):
    definition = models.ForeignKey(Definition, on_delete=models.CASCADE, related_name='names')
    device_name = models.CharField(max_length=64, help_text="SSID or BLE Name")

    def save(self, *args, **kwargs):
        if self.device_name:
            self.device_name = self.device_name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.device_name} ({self.definition.definition_name or 'Rule'})"


def firmware_upload_path(instance, filename):
    # Generates a path like: firmware/firmware-1.0.1-esp32c6.bin
    ext = filename.split('.')[-1]
    new_filename = f"firmware-{instance.release.version}-{instance.hardware_target}.{ext}"
    return os.path.join('firmware/', new_filename)

class FirmwareRelease(models.Model):
    version = models.CharField(max_length=32, unique=True, help_text="e.g., '1.0.1'")
    is_active = models.BooleanField(default=True, help_text="Set as the current active release for the fleet")
    release_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, help_text="Changelog or release notes")

    def __str__(self):
        return f"Firmware v{self.version}"

class FirmwareBinary(models.Model):
    CHIP_CHOICES = [
        ('esp32c3', 'ESP32-C3'),
        ('esp32c5', 'ESP32-C5'),
        ('esp32c6', 'ESP32-C6'),
        ('esp32s3', 'ESP32-S3'),
        ('esp32', 'ESP32 Legacy'),
    ]
    release = models.ForeignKey(FirmwareRelease, on_delete=models.CASCADE, related_name='binaries')
    hardware_target = models.CharField(max_length=32, choices=CHIP_CHOICES)
    binary_file = models.FileField(upload_to=firmware_upload_path, help_text="Upload the UNENCRYPTED .bin file here")

    class Meta:
        unique_together = ('release', 'hardware_target')

    def __str__(self):
        return f"{self.hardware_target} binary for v{self.release.version}"
