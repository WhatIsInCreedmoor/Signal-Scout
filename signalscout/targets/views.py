import json
from .models import Target, Watcher, TrackedTarget, DeviceMAC, DeploymentLocation, FalsePositiveFilter, Definition, DefinitionOUI, DefinitionName, FirmwareRelease
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.shortcuts import render
from datetime import timedelta
from django.db.models import Q
from django.conf import settings
import hashlib
from django.views.decorators.http import require_GET
from django.http import FileResponse
import os

def map_view(request):
    context = {
        'site_name': settings.SITE_NAME,
        'map_lat': settings.MAP_CENTER_LAT,
        'map_lon': settings.MAP_CENTER_LON,
        'map_zoom': settings.MAP_DEFAULT_ZOOM,
    }
    return render(request, 'targets/map.html', context)

@csrf_exempt
def ingest_target(request):
    print("RAW BODY:", request.body.decode('utf-8'))
    if request.method != 'POST':
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return JsonResponse({"status": "error", "message": "API key required"}, status=401)

    try:
        watcher = Watcher.objects.get(auth_key=api_key, is_active=True)
        watcher.last_seen = timezone.now()
        watcher.save()
    except Watcher.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Invalid or inactive API key"}, status=403)

    try:
        data = json.loads(request.body)

        # BACKWARDS COMPATIBILITY: Legacy nodes sending heartbeat via ingest endpoint
        if data.get('device_name') == "HEARTBEAT":
            heartbeat_mac = data.get('mac_address')
            if heartbeat_mac and heartbeat_mac != "00:00:00:00:00:00":
                if not watcher.mac_address or watcher.mac_address != heartbeat_mac:
                    watcher.mac_address = heartbeat_mac
                    watcher.save(update_fields=['mac_address'])
            return JsonResponse({"status": "success", "message": "Legacy heartbeat acknowledged"}, status=200)

        # 1. Get the area from the Watcher database
        area = watcher.deployment_location.name if watcher.deployment_location else "Unknown Area"

        # 2. Get coordinates from payload
        lat = data.get('latitude')
        lon = data.get('longitude')

        # 3. Fallback to the DeploymentLocation database
        if lat is None or lon is None:
            try:
                location = DeploymentLocation.objects.get(name=area)
                lat = location.latitude
                lon = location.longitude
            except DeploymentLocation.DoesNotExist:
                lat, lon = 0.0, 0.0

        incoming_mac = data['mac_address']

        # Look for a match in the known DB
        known_mac = DeviceMAC.objects.filter(mac_address=incoming_mac).first()
        known_device = known_mac.tracked_target if known_mac else None

        # Default to payload data
        final_operator = data.get('operator')
        final_device_name = data.get('device_name')
        final_confidence = data.get('confidence')

        # Override with specific known targets if they exist
        if known_device:
            if known_device.operator:
                final_operator = known_device.operator
            final_confidence = 'high'

        # Look up the rule in Definitions to assign operator and confidence
        else:
            def_match = None

            # Check for a Device Name match first (more specific)
            if final_device_name:
                name_match = DefinitionName.objects.filter(
                    definition__is_active=True,
                    definition__definition_type=Definition.INCLUDE,
                    device_name__iexact=final_device_name
                ).select_related('definition').first()
                if name_match:
                    def_match = name_match.definition

            # Fallback to OUI match if no name matched
            if not def_match and incoming_mac:
                mac_prefix = incoming_mac[:8].lower() # Grab the XX:XX:XX part

                oui_match = DefinitionOUI.objects.filter(
                    definition__is_active=True,
                    definition__definition_type=Definition.INCLUDE,
                    oui=mac_prefix
                ).select_related('definition').first()

                # If no exact match, see if this is a Virtual MAC from a vmac_expansion rule
                if not oui_match and mac_prefix[0] in ['2', '6', 'a', 'e']:
                    rest_of_oui = mac_prefix[2:] # grab the ':XX:XX' part
                    vmac_rules = DefinitionOUI.objects.filter(
                        definition__is_active=True,
                        definition__definition_type=Definition.INCLUDE,
                        vmac_expansion=True
                    ).select_related('definition')

                    for rule in vmac_rules:
                        if rule.oui.lower()[2:] == rest_of_oui:
                            oui_match = rule
                            break

                if oui_match:
                    def_match = oui_match.definition

            # Apply the definition metadata if found
            if def_match:
                if def_match.operator:
                    final_operator = def_match.operator  # Overrides ESP32 payload
                if def_match.confidence:
                    final_confidence = def_match.confidence # Overrides ESP32 payload

        # False Positive pre-ingest filter
        incoming_mac = incoming_mac.lower()
        incoming_name = (data.get('device_name') or '').lower()

        filters = FalsePositiveFilter.objects.filter(is_active=True)
        for f in filters:
            if f.mac_address and f.mac_address.lower() == incoming_mac:
                return JsonResponse({"status": "ignored", "message": "Dropped by exact MAC rule"}, status=200)
            if f.mac_oui and incoming_mac.startswith(f.mac_oui.lower()):
                return JsonResponse({"status": "ignored", "message": "Dropped by OUI rule"}, status=200)
            if f.device_name and f.device_name.lower() in incoming_name:
                return JsonResponse({"status": "ignored", "message": "Dropped by Device Name rule"}, status=200)

        target = Target.objects.create(
            tracked_target=known_device,
            timestamp=parse_datetime(data.get('timestamp')) if data.get('timestamp') else timezone.now(),
            mac_address=data['mac_address'],
            network_type=data['network_type'],
            channel=data.get('channel'),
            signal_strength=data.get('signal_strength'),
            latitude=lat,
            longitude=lon,
            device_name=final_device_name,
            manufacturer=data.get('manufacturer'),
            user_description=data.get('user_description'),
            area=area,
            operator=final_operator,
            confidence=final_confidence,
            uploaded_by=watcher,
        )

        watcher.last_uploaded = timezone.now()
        watcher.save(update_fields=['last_uploaded'])

        return JsonResponse({"status": "success", "id": target.id}, status=201)
    except Exception as e:
        print("INGEST ERROR:", str(e))
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

def get_targets(request):
    time_threshold = timezone.now() - timedelta(hours=12)

    targets = Target.objects.filter(timestamp__gte=time_threshold).exclude(
        Q(device_name__icontains='test') |
        Q(mac_address__icontains='test') |
        Q(area__icontains='test')
    ).order_by('timestamp')

    # 1. Fetch current deployment locations into a quick-lookup dictionary
    loc_map = {loc.name: (loc.latitude, loc.longitude) for loc in DeploymentLocation.objects.all()}

    grouped_data = {}
    for t in targets:
        group_key = f"target_{t.tracked_target_id}" if t.tracked_target_id else f"mac_{t.mac_address}"
        if group_key not in grouped_data:
            grouped_data[group_key] = []
        grouped_data[group_key].append(t)

    sessions = []

    for g_key, target_list in grouped_data.items():
        current_session = None
        for t in target_list:
            # 2. Look up the dynamic coordinates from the map, fallback to saved Target coords if missing
            dynamic_lat, dynamic_lon = loc_map.get(t.area, (t.latitude, t.longitude))

            if current_session is None:
                current_session = {
                    'id': t.id,
                    'first_seen': t.timestamp,
                    'last_seen': t.timestamp,
                    'mac_address': t.mac_address,
                    'network_type': t.network_type,
                    'latitude': dynamic_lat,
                    'longitude': dynamic_lon,
                    'device_name': t.device_name or '',
                    'manufacturer': t.manufacturer or '',
                    'area': t.area or '',
                    'operator': t.operator or '',
                    'confidence': t.confidence or '',
                }
            else:
                time_gap = t.timestamp - current_session['last_seen']

                # Check BOTH the time gap and whether the physical scanner area changed
                if time_gap <= timedelta(minutes=5) and (t.area or '') == current_session['area']:
                    current_session['last_seen'] = t.timestamp
                    current_session['latitude'] = dynamic_lat
                    current_session['longitude'] = dynamic_lon
                    current_session['confidence'] = t.confidence or ''

                    if t.network_type and t.network_type not in current_session['network_type']:
                        current_session['network_type'] += f", {t.network_type}"
                else:
                    sessions.append(current_session)
                    current_session = {
                        'id': t.id, 'first_seen': t.timestamp, 'last_seen': t.timestamp,
                        'mac_address': t.mac_address, 'network_type': t.network_type,
                        'latitude': dynamic_lat, 'longitude': dynamic_lon,
                        'device_name': t.device_name or '', 'manufacturer': t.manufacturer or '',
                        'area': t.area or '', 'operator': t.operator or '', 'confidence': t.confidence or ''
                    }
        if current_session:
            sessions.append(current_session)

    sessions.sort(key=lambda x: x['last_seen'], reverse=True)

    for s in sessions:
        s['first_seen'] = s['first_seen'].isoformat()
        s['last_seen'] = s['last_seen'].isoformat()

    return JsonResponse({'targets': sessions})

@csrf_exempt
def heartbeat(request):
    if request.method != 'POST':
        return JsonResponse({"status": "error", "message": "Method not allowed. Use POST."}, status=405)

    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return JsonResponse({"status": "error", "message": "API key required"}, status=401)

    try:
        watcher = Watcher.objects.get(auth_key=api_key, is_active=True)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}

        # Default to the version already in the DB if the device omits it
        current_version = data.get('firmware_version', watcher.firmware_version)
        hw_target = data.get('hardware_target')

        watcher.firmware_version = current_version
        if hw_target:
            watcher.hardware_target = hw_target

        watcher.last_seen = timezone.now()

        mac = data.get('mac_address')
        if mac and mac != "00:00:00:00:00:00":
            watcher.mac_address = mac

        watcher.save(update_fields=['last_seen', 'firmware_version', 'hardware_target', 'mac_address'])

        response_payload = {"status": "success", "message": "Heartbeat received"}

# New OTA Check Logic (Relational Architecture)
        if hasattr(watcher, 'auto_update_enabled') and watcher.auto_update_enabled and watcher.hardware_target:
            # 1. Get the top-level active release (Do NOT filter by hardware_target here)
            latest_fw = FirmwareRelease.objects.filter(is_active=True).order_by('-release_date').first()

            if latest_fw and current_version != latest_fw.version:
                # 2. Query the child binaries for the specific hardware target
                target_binary = latest_fw.binaries.filter(hardware_target=watcher.hardware_target).first()

                if target_binary:
                    # Force HTTPS to prevent double-connecting and TLS overhead
                    raw_url = request.build_absolute_uri(target_binary.binary_file.url)
                    response_payload['ota_url'] = raw_url.replace("http://", "https://", 1)
                    response_payload['target_version'] = latest_fw.version

        return JsonResponse(response_payload, status=200)

    except Watcher.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Invalid or inactive API key"}, status=403)

@require_GET
def get_definitions(request):
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return JsonResponse({"status": "error", "message": "API key required"}, status=401)

    try:
        watcher = Watcher.objects.get(auth_key=api_key, is_active=True)
        watcher.last_seen = timezone.now()
        watcher.save(update_fields=['last_seen'])
    except Watcher.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Invalid or inactive API key"}, status=403)

    # 1. Target OUIs (Includes VMAC Expansion)
    target_oui_records = DefinitionOUI.objects.filter(
        definition__is_active=True,
        definition__definition_type=Definition.INCLUDE
    ).values('oui', 'vmac_expansion')

    expanded_target_ouis = set()
    for record in target_oui_records:
        base_oui = record['oui'].lower()
        expanded_target_ouis.add(base_oui)
        if record.get('vmac_expansion'):
            upper_nibble = base_oui[0]
            rest_of_oui = base_oui[2:]
            for lower_nibble in ['2', '6', 'a', 'e']:
                expanded_target_ouis.add(f"{upper_nibble}{lower_nibble}{rest_of_oui}")
    target_ouis = list(expanded_target_ouis)

    # 2. Target Names
    target_names = list(DefinitionName.objects.filter(
        definition__is_active=True,
        definition__definition_type=Definition.INCLUDE
    ).values_list('device_name', flat=True))

    # 3. Ignore OUIs
    ignore_ouis = list(DefinitionOUI.objects.filter(
        definition__is_active=True,
        definition__definition_type=Definition.EXCLUDE
    ).values_list('oui', flat=True))

    # 4. Ignore Names
    ignore_names = list(DefinitionName.objects.filter(
        definition__is_active=True,
        definition__definition_type=Definition.EXCLUDE
    ).values_list('device_name', flat=True))

    # 5. False Positive Filters
    fp_filters = FalsePositiveFilter.objects.filter(is_active=True)
    ignore_ouis.extend(list(fp_filters.exclude(mac_oui__isnull=True).exclude(mac_oui__exact='').values_list('mac_oui', flat=True)))
    ignore_names.extend(list(fp_filters.exclude(device_name__isnull=True).exclude(device_name__exact='').values_list('device_name', flat=True)))

    # Fetch unique MACs from the DeviceMAC model linked to TrackedTarget
    tracked_macs = list(DeviceMAC.objects.values_list('mac_address', flat=True).distinct())

    payload = {
        'target_ouis': sorted(list(set(target_ouis))),
        'target_names': sorted(list(set(target_names))),
        'ignore_ouis': sorted(list(set(ignore_ouis))),
        'ignore_names': sorted(list(set(ignore_names))),
    }

    response_data = json.dumps(payload, separators=(',', ':'))
    etag = hashlib.md5(response_data.encode('utf-8')).hexdigest()

    if request.headers.get('If-None-Match') == etag:
        return JsonResponse({}, status=304)

    response = JsonResponse(payload)
    response['ETag'] = etag
    return response

@require_GET
def serve_firmware(request, path):
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return JsonResponse({"status": "error", "message": "API key required"}, status=401)

    try:
        watcher = Watcher.objects.get(auth_key=api_key, is_active=True)
    except Watcher.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Invalid or inactive API key"}, status=403)

    file_path = os.path.join(settings.BASE_DIR, 'firmware', path)

    if os.path.exists(file_path):
        # 1. Open the file
        file_obj = open(file_path, 'rb')
        response = FileResponse(file_obj, content_type='application/octet-stream')

        # 2. CRITICAL: Force Content-Length to prevent chunked transfer encoding drops
        response['Content-Length'] = os.path.getsize(file_path)
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'

        return response
    else:
        return JsonResponse({"status": "error", "message": "Firmware file not found"}, status=404)
