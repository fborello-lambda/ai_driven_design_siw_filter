"""Read-only diagnostics of a live Gmsh model, before gmsh.finalize()."""
from __future__ import annotations

import numpy as np
import gmsh


def inspect_mesh() -> dict:
    """Report CAD boundary coverage and actual linear-tet/port mesh quality.

    An assigned boundary is not proof that it is physically correct. This
    report deliberately retains each surface's geometry and adjacency for
    an independent review of the labels.
    """
    surfaces = []
    for dim, tag in gmsh.model.getEntities(2):
        surfaces.append({
            "tag": tag, "type": gmsh.model.getType(dim, tag),
            "area_mm2": gmsh.model.occ.getMass(dim, tag),
            "centroid_mm": list(gmsh.model.occ.getCenterOfMass(dim, tag)),
            "bbox_mm": list(gmsh.model.getBoundingBox(dim, tag)),
            "volumes": gmsh.model.getAdjacencies(dim, tag)[0].tolist(),
            "groups": gmsh.model.getPhysicalGroupsForEntity(dim, tag).tolist(),
        })
    tet_tags, tet_nodes = gmsh.model.mesh.getElementsByType(4)
    if not len(tet_tags):
        raise RuntimeError("Empty tetrahedral mesh")
    quality = gmsh.model.mesh.getElementQualities(tet_tags, "minSICN")
    node_tags, xyz, _ = gmsh.model.mesh.getNodes()
    coordinates = dict(zip(node_tags.tolist(), np.asarray(xyz).reshape(-1, 3)))
    nodes = np.asarray(tet_nodes).reshape(-1, 4)
    worst = np.argsort(quality)[:10]
    ports = {}
    for attr in (11, 12):
        faces = [s for s in surfaces if attr in s["groups"]]
        triangles = []
        for face in faces:
            _, tri_nodes = gmsh.model.mesh.getElementsByType(2, face["tag"])
            triangles.extend(np.asarray(tri_nodes).reshape(-1, 3).tolist())
        area = sum(float(np.linalg.norm(np.cross(coordinates[b] - coordinates[a],
                                                 coordinates[c] - coordinates[a])) / 2)
                   for a, b, c in triangles)
        ports[str(attr)] = {"cad_area_mm2": sum(s["area_mm2"] for s in faces),
                            "mesh_area_mm2": area, "triangles": len(triangles),
                            "nodes": len({n for t in triangles for n in t}),
                            "one_sided": all(len(s["volumes"]) == 1 for s in faces)}
    return {
        "tetrahedra": len(tet_tags), "nodes": len(node_tags),
        "quality": {"metric": "minSICN", "min": float(quality.min()),
                    "p01_p05_p50": np.percentile(quality, [1, 5, 50]).tolist(),
                    "nonpositive": int(np.sum(quality <= 0)),
                    "below_0p01": int(np.sum(quality < .01)),
                    "worst": [{"element": int(tet_tags[i]), "quality": float(quality[i]),
                               "centroid_mm": np.mean([coordinates[n] for n in nodes[i]], axis=0).tolist()}
                              for i in worst]},
        "unclassified_exterior": [s["tag"] for s in surfaces
                                   if len(s["volumes"]) <= 1 and not s["groups"]],
        "ports": ports, "surfaces": surfaces,
        "volumes": [{"tag": tag, "volume_mm3": gmsh.model.occ.getMass(dim, tag),
                     "groups": gmsh.model.getPhysicalGroupsForEntity(dim, tag).tolist()}
                    for dim, tag in gmsh.model.getEntities(3)],
    }
