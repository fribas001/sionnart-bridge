"""Geometric vegetation descriptors; no radio attenuation model is inferred.

Coordinates follow the exporter's metre convention. The corridor is a square
prism along the straight TX--RX segment, not a Fresnel zone or a traced path.
"""
import math
import numpy as np

SCHEMA = 'sionna_vegetation_metrics'
try:
    from .vegetation_fields import FIELDS
except ImportError:
    from vegetation_fields import FIELDS


def leaf_topology(faces, roles, ids=None, convention='AUTO'):
    """Components share vertices, not spatial proximity; face IDs must be >0.

    Closed components use half surface area in AUTO. Open components use the
    full single-sheet area. Islands are estimates, never biological identities.
    """
    parent = {}
    def find(v):
        parent.setdefault(v, v)
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    leaf = [i for i, role in enumerate(roles) if role == 'leaf']
    for i in leaf:
        face = faces[i]
        for v in face[1:]: parent[find(v)] = find(face[0])
    components = {}
    for i in leaf:
        components.setdefault(find(faces[i][0]), []).append(i)
    factors = np.ones(len(faces), dtype=float)
    closed = 0
    nonmanifold = False
    for indices in components.values():
        edges = {}
        for i in indices:
            face = faces[i]
            for j, a in enumerate(face):
                edge = tuple(sorted((a, face[(j+1) % len(face)])))
                edges[edge] = edges.get(edge, 0) + 1
        is_closed = bool(edges) and all(n == 2 for n in edges.values())
        nonmanifold |= any(n > 2 for n in edges.values())
        closed += int(is_closed)
        factor = .5 if convention == 'HALF_SURFACE' or (convention == 'AUTO' and is_closed) else 1.
        factors[indices] = factor
    tagged = len({int(ids[i]) for i in leaf}) if ids is not None and all(ids[i] > 0 for i in leaf) else (0 if not leaf else None)
    return factors, len(components), tagged, closed, nonmanifold


def areas(triangles):
    return .5 * np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0]), axis=1)


def bounds_metrics(lo, hi, leaf_area):
    size = np.maximum(0., np.asarray(hi)-lo)
    volume, footprint = float(np.prod(size)), float(size[0]*size[1])
    return {'vegetation_bounds_volume_m3': volume,
            'vegetation_bounds_footprint_m2': footprint,
            'leaf_area_density_bbox_m_inv': leaf_area/volume if volume > 1e-12 else None,
            'leaf_area_index_bbox': leaf_area/footprint if footprint > 1e-12 else None}


def box_interval(start, end, lo, hi):
    """Clipped interval in metres, including TX or RX inside vegetation bounds."""
    start, end, lo, hi = map(lambda x: np.asarray(x, dtype=float), (start,end,lo,hi))
    delta = end-start
    length = float(np.linalg.norm(delta))
    if length <= 1e-12: return None
    near, far = 0., 1.
    for i in range(3):
        if abs(delta[i]) < 1e-14:
            if start[i] < lo[i] or start[i] > hi[i]: return None
        else:
            a,b = sorted(((lo[i]-start[i])/delta[i], (hi[i]-start[i])/delta[i]))
            near,far = max(near,a),min(far,b)
            if far <= near: return None
    return (near*length, far*length) if far > near else None


def union_length(intervals):
    intervals = sorted(i for i in intervals if i is not None)
    if not intervals: return 0.
    a,b = intervals[0]; total = 0.
    for c,d in intervals[1:]:
        if c > b: total += b-a; a,b = c,d
        else: b = max(b,d)
    return total+b-a


def surface_hits(triangles, start, end):
    """Two-sided segment/triangle tests. Shared-edge/coincident hits merge.

    Tangent coplanar segments and the segment endpoints do not count. These
    are surface crossings, not leaf counts or Sionna propagation interactions.
    """
    delta = np.asarray(end)-start; length = float(np.linalg.norm(delta))
    if not len(triangles) or length <= 1e-12: return []
    direction = delta/length
    e1 = triangles[:,1]-triangles[:,0]; e2 = triangles[:,2]-triangles[:,0]
    p = np.cross(direction, e2); det = np.einsum('ij,ij->i',e1,p)
    tol = 1e-12*np.linalg.norm(e1,axis=1)*np.linalg.norm(e2,axis=1)
    good = np.abs(det) > np.maximum(1e-30,tol)
    inv = np.zeros_like(det); inv[good] = 1./det[good]
    t = np.asarray(start)-triangles[:,0]; u = np.einsum('ij,ij->i',t,p)*inv
    q = np.cross(t,e1); v = q@direction*inv; dist = np.einsum('ij,ij->i',e2,q)*inv
    good &= (u >= -1e-9)&(v >= -1e-9)&(u+v <= 1+1e-9)&(dist > 1e-7)&(dist < length-1e-7)
    hits = sorted(float(x) for x in dist[good])
    return merge_hits(hits)


def merge_hits(hits):
    out = []
    for d in sorted(hits):
        if not out or d-out[-1] > 1e-6: out.append(d)
    return out


def corridor_area(triangles, factors, start, end, width):
    """Exact triangle clipping to square corridor, with area convention factors.

    Most triangles are rejected or wholly accepted with vectorized tests.
    The local x axis is cross(direction, world Z), or world Y near vertical.
    """
    start,end = np.asarray(start),np.asarray(end)
    length = float(np.linalg.norm(end-start))
    if length <= 1e-12: return None
    if not len(triangles): return 0.
    z = (end-start)/length
    anchor = np.array([0.,0.,1.]) if abs(z[2]) < .99 else np.array([0.,1.,0.])
    x = np.cross(z,anchor); x /= np.linalg.norm(x); y = np.cross(z,x)
    local = (triangles-start)@np.stack([x,y,z],axis=1)
    lo,hi = np.array([-width/2,-width/2,0.]),np.array([width/2,width/2,length])
    mn,mx = local.min(axis=1),local.max(axis=1)
    intersects = np.all(mx >= lo,axis=1)&np.all(mn <= hi,axis=1)
    inside = np.all(mn >= lo,axis=1)&np.all(mx <= hi,axis=1)
    total = float(np.sum(areas(local[inside])*factors[inside]))
    for tri,factor in zip(local[intersects&~inside], factors[intersects&~inside]):
        polygon = list(tri)
        for axis in range(3):
            for bound,sign in [(lo[axis],1),(hi[axis],-1)]:
                clipped = []
                if not polygon: break
                a = polygon[-1]; da = sign*(a[axis]-bound)
                for b in polygon:
                    db = sign*(b[axis]-bound)
                    if (da >= 0) != (db >= 0): clipped.append(a+(b-a)*(da/(da-db)))
                    if db >= 0: clipped.append(b)
                    a,da = b,db
                polygon = clipped
        if len(polygon) >= 3:
            total += float(sum(np.linalg.norm(np.cross(polygon[i]-polygon[0],polygon[i+1]-polygon[0]))/2 for i in range(1,len(polygon)-1)))*factor
    return total


def measure_packets(packets, transmitters, receivers, width=1.):
    """Packets are evaluated instance meshes grouped by their generating object."""
    if not math.isfinite(width) or width <= 0: raise ValueError('Corridor width must be positive and finite')
    objects = []
    groups = {}
    for p in packets: groups.setdefault(p['owner'],[]).append(p)
    totals = {'leaf_surface_area_m2':0.,'leaf_area_estimate_m2':0.,'wood_surface_area_m2':0.,
              'leaf_component_count':0,'tagged_leaf_count':0}
    for owner, ps in sorted(groups.items()):
        metrics = dict.fromkeys(totals,0)
        for p in ps:
            for k in metrics:
                value = p['metrics'][k]
                metrics[k] = metrics[k]+value if metrics[k] is not None and value is not None else None
        lo = np.min([p['lo'] for p in ps],axis=0); hi = np.max([p['hi'] for p in ps],axis=0)
        for k in totals:
            totals[k] = totals[k]+metrics[k] if totals[k] is not None and metrics[k] is not None else None
        metrics.update(bounds_metrics(lo,hi,metrics['leaf_area_estimate_m2']))
        objects.append({'name':owner,'evaluated_mesh_instances':len(ps),
                        'source_meshes':sorted({p['source'] for p in ps}),
                        'bounds_min_m':lo.tolist(),'bounds_max_m':hi.tolist(),'metrics':metrics})
    if packets:
        totals.update(bounds_metrics(np.min([p['lo'] for p in packets],axis=0),np.max([p['hi'] for p in packets],axis=0),totals['leaf_area_estimate_m2']))
    else:
        totals.update(bounds_metrics([0.,0.,0.],[0.,0.,0.],0.))
    links = []
    for tx in transmitters:
        for rx in receivers:
            start,end = np.asarray(tx['position']),np.asarray(rx['position'])
            length = float(np.linalg.norm(end-start)); volume = width*width*length
            per_object = []; intervals = []; all_leaf_hits = []; all_wood_hits = []; area_total = 0.
            for obj in objects:
                ps = groups[obj['name']]; interval = box_interval(start,end,obj['bounds_min_m'],obj['bounds_max_m'])
                intervals.append(interval); lh=[];wh=[]; area=0.
                for p in ps:
                    lh.extend(surface_hits(p['leaf_triangles'],start,end)); wh.extend(surface_hits(p['wood_triangles'],start,end))
                    area += corridor_area(p['leaf_triangles'],p['leaf_factors'],start,end,width) or 0.
                all_leaf_hits.extend(lh);all_wood_hits.extend(wh);area_total += area
                per_object.append({'name':obj['name'],'metrics':{
                    'vegetation_bounds_length_m':union_length([interval]),
                    'leaf_surface_crossings':len(merge_hits(lh)) if length else None,
                    'wood_surface_crossings':len(merge_hits(wh)) if length else None,
                    'corridor_leaf_area_m2':area if length else None,
                    'corridor_leaf_area_density_m_inv':area/volume if volume else None}})
            links.append({'tx':tx.get('blender_name',tx['name']),'rx':rx.get('blender_name',rx['name']),
                          'objects':per_object,'metrics':{
                'distance_m':length,'vegetation_bounds_length_m':union_length(intervals),
                'leaf_surface_crossings':len(merge_hits(all_leaf_hits)) if length else None,
                'wood_surface_crossings':len(merge_hits(all_wood_hits)) if length else None,
                'corridor_leaf_area_m2':area_total if length else None,'corridor_volume_m3':volume,
                'corridor_leaf_area_density_m_inv':area_total/volume if volume else None}})
    return {'objects':objects,'scene':totals,'links':links}
