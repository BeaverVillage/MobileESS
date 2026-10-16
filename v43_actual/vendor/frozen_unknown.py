from copy import deepcopy


def _migration_capability(authority, source, destination, gpu):
    if not authority:return None
    routes=[(name,row) for name,row in authority['routes'].items()
            if row['source']==source and row['destination']==destination]
    # Ambiguous routing is unsupported, never choose a path without authority.
    if len(routes)!=1:return None
    name,row=routes[0]
    return dict(source_sha=authority['packet_source_sha'],checkpoint_authorized=True,
        allowed_destinations=[destination],gpu_type_confirmed=True,rack_gang_confirmed=True,
        data_residency_confirmed=True,wan_path=name,bandwidth_bytes_per_second=row['bandwidth_bytes_per_second'],
        payload_bytes=authority['scalar']['bytes_per_GPU']*gpu,
        restart_seconds=authority['scalar']['current_conservative_restart_seconds'],source_wait_seconds=0,
        source_hold_until=authority['protocol']['source_hold_until'],
        destination_hold_from=authority['protocol']['destination_hold_from'],assumption=True,
        route_links=row['links'],measured_Kestrel_capability=False)
