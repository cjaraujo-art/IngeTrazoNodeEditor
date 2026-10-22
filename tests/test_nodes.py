# SPDX-License-Identifier: GPL-3.0-or-later
"""Automated unit test suite for the IngeTrazo Parametric Node Editor."""

import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
_repo_dir = str(Path(__file__).resolve().parent.parent)
if _repo_dir not in sys.path:
    sys.path.insert(0, _repo_dir)

from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, coerce_value
from node_base import BaseNode, InputSpec, OutputSpec, NODE_REGISTRY, register_node
from engine import GraphEngine, Wire
from nodes import discover_nodes
from PySide6.QtWidgets import QApplication
from ui_canvas import NodeItem


class TestCoreGeometry(unittest.TestCase):
    def test_vec3_operations(self):
        v1 = Vec3(1.0, 2.0, 3.0)
        v2 = Vec3(4.0, 5.0, 6.0)
        v3 = v1 + v2
        self.assertEqual(v3, Vec3(5.0, 7.0, 9.0))
        self.assertAlmostEqual(v1.dot(v2), 32.0)
        self.assertAlmostEqual(Vec3(3.0, 4.0, 0.0).length(), 5.0)
        self.assertAlmostEqual(Vec3(0.0, 0.0, 10.0).normalized().length(), 1.0)

    def test_watertight_box(self):
        box = MeshData.create_box(Vec3(0, 0, 0), 2.0, 3.0, 4.0)
        self.assertEqual(len(box.vertices), 8)
        self.assertEqual(len(box.faces), 6)
        # Check that each face has 4 vertices
        for f in box.faces:
            self.assertEqual(len(f), 4)
        # Verify 12 edges
        self.assertEqual(len(box.edges), 12)

    def test_watertight_cylinder(self):
        cyl = MeshData.create_cylinder(Vec3(0, 0, 0), radius=1.0, height=3.0, segments=16)
        self.assertEqual(len(cyl.vertices), 32)
        # 1 bottom + 1 top + 16 side quads = 18 faces
        self.assertEqual(len(cyl.faces), 18)

    def test_mesh_transform_and_merge(self):
        box1 = MeshData.create_box(Vec3(0, 0, 0), 1.0, 1.0, 1.0)
        box2 = box1.transformed(offset=Vec3(10.0, 0.0, 0.0))
        self.assertEqual(box2.vertices[0][0], 10.0)

        merged = MeshData.merge([box1, box2])
        self.assertEqual(len(merged.vertices), 16)
        self.assertEqual(len(merged.faces), 12)

    def test_curve_extrusion(self):
        pts = [Vec3(0, 0, 0), Vec3(2, 0, 0), Vec3(2, 2, 0), Vec3(0, 2, 0)]
        curve = CurveData(points=pts, closed=True)
        extrusion = MeshData.extrude_curve(curve, height=3.0, cap=True)
        self.assertEqual(len(extrusion.vertices), 8)
        self.assertEqual(len(extrusion.faces), 6)  # 4 sides + 2 caps


class TestNodeExecution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_nodes(reload_modules=False)

    def test_registry_populated(self):
        self.assertIn("input.number", NODE_REGISTRY)
        self.assertIn("solid.box", NODE_REGISTRY)
        self.assertIn("solid.cylinder", NODE_REGISTRY)
        self.assertIn("vec.grid_2d", NODE_REGISTRY)
        self.assertIn("scene.output", NODE_REGISTRY)
        self.assertIn("arch.parametric_stair", NODE_REGISTRY)

    def test_auto_broadcasting_longest_list(self):
        engine = GraphEngine()
        g = engine.add_node("vec.grid_2d")
        g.set_param("nx", 2)
        g.set_param("ny", 2)

        c = engine.add_node("solid.cylinder")
        engine.connect(g.id, "points", c.id, "center")

        engine.evaluate()
        cyl_output = c.cached_outputs.get("mesh")
        self.assertIsInstance(cyl_output, list)
        self.assertEqual(len(cyl_output), 4)
        for cyl in cyl_output:
            self.assertIsInstance(cyl, MeshData)


class TestGraphEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_nodes(reload_modules=False)

    def test_cycle_detection(self):
        engine = GraphEngine()
        n1 = engine.add_node("input.number")
        n2 = engine.add_node("transform.move_rot_scale")

        wire1 = engine.connect(n1.id, "out", n2.id, "scale")
        self.assertIsNotNone(wire1)

        # Attempt to create feedback cycle
        can = engine.can_connect(n2.id, "mesh", n1.id, "val")
        self.assertFalse(can)

    def test_dirty_caching(self):
        engine = GraphEngine()
        n1 = engine.add_node("input.number")
        n1.set_param("val", 5.0)

        engine.evaluate()
        self.assertFalse(n1.is_dirty)

        # Modifying parameter marks node dirty
        engine.update_node_param(n1.id, "val", 10.0)
        self.assertTrue(n1.is_dirty)

    def test_serialization(self):
        engine = GraphEngine()
        b = engine.add_node("solid.box")
        b.set_param("dx", 5.0)
        o = engine.add_node("scene.output")
        engine.connect(b.id, "mesh", o.id, "mesh")

        data = engine.to_dict()
        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(len(data["wires"]), 1)

        new_engine = GraphEngine()
        new_engine.load_dict(data)
        self.assertEqual(len(new_engine.nodes), 2)
        self.assertEqual(len(new_engine.wires), 1)

    def test_mute_and_preview_toggle(self):
        engine = GraphEngine()
        b = engine.add_node("solid.box")
        o = engine.add_node("scene.output")
        engine.connect(b.id, "mesh", o.id, "mesh")

        # Evaluate while enabled
        engine.evaluate()
        meshes, points = engine.collect_scene_outputs()
        self.assertGreater(len(meshes), 0)

        # Mute box
        b.is_enabled = False
        engine.mark_dirty(b.id)
        engine.evaluate()
        m_muted, p_muted = engine.collect_scene_outputs()
        self.assertEqual(len(m_muted), 0)
        self.assertEqual(len(p_muted), 0)

        # Re-enable box, mute box and output preview
        b.is_enabled = True
        b.is_preview_visible = False
        o.is_preview_visible = False
        engine.mark_dirty(b.id)
        engine.evaluate()
        m_hidden, p_hidden = engine.collect_scene_outputs()
        self.assertEqual(len(m_hidden), 0)
        self.assertEqual(len(p_hidden), 0)

        # Output node live preview works when output is visible even if upstream node preview is muted
        o.is_preview_visible = True
        engine.mark_dirty(b.id)
        engine.evaluate()
        m_out_vis, _ = engine.collect_scene_outputs()
        self.assertEqual(len(m_out_vis), 1)

        # Mute output node bake
        b.is_preview_visible = True
        o.is_preview_visible = False
        engine.mark_dirty(b.id)
        engine.evaluate()
        bake_muted = engine.collect_bake_outputs()
        self.assertEqual(len(bake_muted), 0)

    def test_copy_paste_duplicate(self):
        import json
        engine = GraphEngine()
        b = engine.add_node("solid.box")
        b.set_param("dx", 8.0)
        o = engine.add_node("scene.output")
        engine.connect(b.id, "mesh", o.id, "mesh")

        # Copy both nodes
        clip = engine.copy_nodes([b.id, o.id])
        clip_data = json.loads(clip)
        self.assertEqual(len(clip_data["nodes"]), 2)
        self.assertEqual(len(clip_data["wires"]), 1)

        # Paste
        pasted_nodes = engine.paste_nodes(clip, offset=(50.0, 50.0))
        self.assertEqual(len(pasted_nodes), 2)
        self.assertEqual(len(engine.nodes), 4)
        self.assertEqual(len(engine.wires), 2)

        # Duplicate
        dup_nodes = engine.duplicate_nodes([b.id], offset=(30.0, 30.0))
        self.assertEqual(len(dup_nodes), 1)
        self.assertEqual(len(engine.nodes), 5)


class TestArchitecturalNodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_nodes(reload_modules=False)

    def test_straight_skeleton_hip_roof(self):
        roof_cls = NODE_REGISTRY["arch.roof"]
        roof = roof_cls()
        # Test Hip (Straight Skeleton) style
        res = roof.compute(boundary=None, pitch=35.0, style=0, overhang=0.4, thickness=0.25, elevation=3.0)
        mesh = res["solid"]
        self.assertIsInstance(mesh, MeshData)
        self.assertGreater(len(mesh.vertices), 0)
        self.assertGreater(len(mesh.faces), 0)
        self.assertGreater(len(res["eaves"].points), 0)

    def test_roof_styles(self):
        roof_cls = NODE_REGISTRY["arch.roof"]
        roof = roof_cls()
        for style_idx in [1, 2, 3, 4]:  # Gable, Shed, Flat, Mansard
            res = roof.compute(boundary=None, pitch=30.0, style=style_idx, overhang=0.2, thickness=0.2, elevation=0.0)
            self.assertGreater(len(res["solid"].faces), 0, f"Roof style {style_idx} produced no faces")

    def test_wall_and_slab(self):
        wall_cls = NODE_REGISTRY["arch.wall"]
        wall = wall_cls()
        rect_curve = CurveData(
            points=[Vec3(0, 0, 0), Vec3(10, 0, 0), Vec3(10, 6, 0), Vec3(0, 6, 0)],
            closed=True,
        )
        wall_res = wall.compute(curve=rect_curve, thickness=0.25, height=3.0, elevation=0.0)
        self.assertGreater(len(wall_res["wall_mesh"].faces), 0)

        slab_cls = NODE_REGISTRY["arch.slab"]
        slab = slab_cls()
        slab_res = slab.compute(boundary=rect_curve, thickness=0.3, elevation=0.0, overhang=0.2)
        self.assertGreater(len(slab_res["slab_mesh"].faces), 0)

    def test_curve_nodes(self):
        circle_cls = NODE_REGISTRY["curve.circle"]
        circle = circle_cls()
        c_res = circle.compute(radius=3.0, segments=32, center=Vec3(0, 0, 0))
        self.assertEqual(len(c_res["curve"].points), 32)
        self.assertGreater(len(c_res["face"].faces), 0)

        star_cls = NODE_REGISTRY["curve.star"]
        star = star_cls()
        s_res = star.compute(inner_radius=1.0, outer_radius=2.0, points_count=5, center=Vec3(0, 0, 0))
        self.assertEqual(len(s_res["curve"].points), 10)

    def test_transform_nodes(self):
        extrude_cls = NODE_REGISTRY["solid.extrude"]
        extrude = extrude_cls()
        rect = CurveData(points=[Vec3(0,0,0), Vec3(2,0,0), Vec3(2,2,0), Vec3(0,2,0)], closed=True)
        e_res = extrude.compute(curve=rect, height=4.0, capped=True)
        self.assertGreater(len(e_res["solid"].faces), 0)

        revolve_cls = NODE_REGISTRY["solid.revolve"]
        revolve = revolve_cls()
        profile = CurveData(points=[Vec3(1,0,0), Vec3(2,0,1), Vec3(1,0,2)], closed=False)
        r_res = revolve.compute(curve=profile, angle=360.0, segments=16)
        self.assertGreater(len(r_res["solid"].faces), 0)

        array_cls = NODE_REGISTRY["xform.linear_array"]
        arr = array_cls()
        box = MeshData.create_box(Vec3(0,0,0), 1, 1, 1)
        a_res = arr.compute(geometry=box, count=3, step=Vec3(2, 0, 0))
        self.assertEqual(len(a_res["array"]), 3)


class TestReferenceFaceAndRoofIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_nodes(reload_modules=False)

    def test_reference_face_fallback_and_structure(self):
        rf_cls = NODE_REGISTRY["scene.reference_face"]
        rf = rf_cls()
        res = rf.compute()
        surface = res["surface"]
        self.assertIn("outer", surface)
        self.assertIn("holes", surface)
        self.assertGreaterEqual(len(surface["outer"]), 3)
        self.assertGreaterEqual(len(surface["holes"]), 1)
        self.assertGreater(len(res["mesh"].faces), 0)

    def test_reference_face_to_roof_pipeline(self):
        engine = GraphEngine()
        rf = engine.add_node("scene.reference_face")
        roof = engine.add_node("arch.roof")
        wire = engine.connect(rf.id, "surface", roof.id, "boundary")
        self.assertIsNotNone(wire)
        engine.evaluate()
        roof_mesh = roof.cached_outputs.get("solid")
        self.assertIsInstance(roof_mesh, MeshData)
        self.assertGreater(len(roof_mesh.faces), 0)
        self.assertGreater(len(roof_mesh.vertices), 0)

    def test_reference_face_stored_state_serialization(self):
        engine = GraphEngine()
        rf = engine.add_node("scene.reference_face")
        custom_face = {
            "outer": [(0, 0, 4), (10, 0, 4), (10, 8, 4), (0, 8, 4)],
            "holes": [[(3, 3, 4), (7, 3, 4), (7, 5, 4), (3, 5, 4)]],
            "base_z": 4.0,
        }
        rf.param_values["stored_face"] = custom_face
        saved = engine.to_dict()

        engine2 = GraphEngine()
        engine2.load_dict(saved)
        rf2 = engine2.get_node(rf.id)
        self.assertIsNotNone(rf2)
        self.assertIn("stored_face", rf2.param_values)
        self.assertEqual(len(rf2.param_values["stored_face"]["outer"]), 4)


class TestCatalogNodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import math
        discover_nodes(reload_modules=False)

    def test_sphere_solid(self):
        sphere_cls = NODE_REGISTRY["solid.sphere"]
        sphere = sphere_cls()
        res = sphere.compute(center=Vec3(0, 0, 0), radius=2.5, rings=10, segments=16)
        m = res["mesh"]
        self.assertIsInstance(m, MeshData)
        self.assertGreater(len(m.vertices), 0)
        self.assertGreater(len(m.faces), 0)
        # Verify Euler characteristic for closed sphere V - E + F = 2
        v = len(m.vertices)
        f = len(m.faces)
        e = len(m.edges)
        self.assertEqual(v - e + f, 2, f"Sphere is not watertight: V={v}, E={e}, F={f}")

    def test_mesh_from_points(self):
        import math
        mfp_cls = NODE_REGISTRY["solid.mesh_from_points"]
        mfp = mfp_cls()
        pts = [
            Vec3(x, y, math.sin(x) * 0.5)
            for x in range(4)
            for y in range(5)
        ]
        # Quad mesh
        res = mfp.compute(points=pts, u=4, v=5, closed_u=False, closed_v=False, swap_uv=False, triangulate=False)
        m = res["mesh"]
        self.assertEqual(len(m.faces), (4 - 1) * (5 - 1))

        # Triangulated mesh
        res_tri = mfp.compute(points=pts, u=4, v=5, closed_u=False, closed_v=False, swap_uv=False, triangulate=True)
        self.assertEqual(len(res_tri["mesh"].faces), (4 - 1) * (5 - 1) * 2)

    def test_point_deconstruct_distance_and_math(self):
        decon = NODE_REGISTRY["vec.deconstruct"]()
        d_res = decon.compute(pt=Vec3(1.5, -2.0, 3.25))
        self.assertEqual(d_res["x"], 1.5)
        self.assertEqual(d_res["y"], -2.0)
        self.assertEqual(d_res["z"], 3.25)

        dist_node = NODE_REGISTRY["vec.distance"]()
        dist_res = dist_node.compute(a=Vec3(0, 0, 0), b=Vec3(3, 4, 0))
        self.assertAlmostEqual(dist_res["dist"], 5.0)

        vmath = NODE_REGISTRY["vec.math"]()
        add_res = vmath.compute(a=Vec3(1, 2, 3), b=Vec3(4, 5, 6), op="Add")
        self.assertEqual(add_res["vec"], Vec3(5, 7, 9))

    def test_math_operators_and_domain(self):
        add_node = NODE_REGISTRY["math.add"]()
        self.assertEqual(add_node.compute(a=10.5, b=4.5)["res"], 15.0)
        self.assertEqual(add_node.compute(a=Vec3(1, 2, 3), b=2.0)["res"], Vec3(3, 4, 5))

        sub_node = NODE_REGISTRY["math.subtract"]()
        self.assertEqual(sub_node.compute(a=10.0, b=3.0)["res"], 7.0)

        mul_node = NODE_REGISTRY["math.multiply"]()
        self.assertEqual(mul_node.compute(a=4.0, b=2.5)["res"], 10.0)

        div_node = NODE_REGISTRY["math.divide"]()
        self.assertEqual(div_node.compute(a=10.0, b=2.0)["res"], 5.0)

        div_dom = NODE_REGISTRY["math.divide_domain"]()
        dd_res = div_dom.compute(start=0.0, end=10.0, count=5)
        self.assertEqual(len(dd_res["seq"]), 6)
        self.assertEqual(dd_res["step"], 2.0)

        cross_ref = NODE_REGISTRY["math.cross_reference"]()
        cr_res = cross_ref.compute(list_a=[1, 2], list_b=["a", "b", "c"])
        self.assertEqual(len(cr_res["a_out"]), 6)
        self.assertEqual(cr_res["a_out"], [1, 1, 1, 2, 2, 2])
        self.assertEqual(cr_res["b_out"], ["a", "b", "c", "a", "b", "c"])

    def test_inputs_and_panel(self):
        panel = NODE_REGISTRY["input.panel"]()
        p_res = panel.compute(data=[10, 20, 30], text="")
        self.assertIn("[0] 10", p_res["text"])
        self.assertEqual(p_res["out"], [10, 20, 30])

        txt_res = panel.compute(data=None, text="12.5\n42\ntrue")
        self.assertEqual(txt_res["out"], [12.5, 42, True])

        int_slider = NODE_REGISTRY["input.integer"]()
        self.assertEqual(int_slider.compute(val=7.4)["out"], 7)

        toggle = NODE_REGISTRY["input.toggle"]()
        self.assertEqual(toggle.compute(val=True)["out"], True)

        str_node = NODE_REGISTRY["input.string"]()
        self.assertEqual(str_node.compute(text="test")["out"], "test")

        # Test ImageSamplerNode procedural fallback
        img_node = NODE_REGISTRY["input.image_sampler"]()
        img_res = img_node.compute(
            path="",
            size_x=8.0,
            size_y=8.0,
            min_z=0.0,
            max_z=1.5,
            count_u=5,
            count_v=5,
            invert=False,
        )
        self.assertEqual(len(img_res["points"]), 25)
        self.assertEqual(len(img_res["values"]), 25)
        self.assertIsInstance(img_res["mesh"], MeshData)
        self.assertEqual(len(img_res["mesh"].faces), 16)

    def test_line_and_face_from_points(self):
        import math
        line_cls = NODE_REGISTRY["curve.line"]
        line = line_cls()
        l_res = line.compute(start=Vec3(0, 0, 0), end=Vec3(5, 5, 0))
        self.assertEqual(len(l_res["curve"].points), 2)
        self.assertAlmostEqual(l_res["length"], math.sqrt(50))

        face_cls = NODE_REGISTRY["curve.face_from_points"]
        face = face_cls()
        pts = [Vec3(0, 0, 0), Vec3(10, 0, 0), Vec3(10, 10, 0), Vec3(0, 10, 0)]
        f_res = face.compute(points=pts)
        self.assertGreater(len(f_res["face"].faces), 0)


class TestMaterialAndPreviewSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_nodes(reload_modules=False)

    def test_assign_material_glass_and_wood(self):
        mat_cls = NODE_REGISTRY["mat.assign"]
        mat_node = mat_cls()

        # 1. Assign Glass
        box_glass = MeshData.create_box(Vec3(0, 0, 0), 1.0, 0.1, 1.5)
        res_glass = mat_node.compute(
            geometry=box_glass,
            material="Glass",
            name="",
            color_r=0.7,
            color_g=0.85,
            color_b=0.95,
            opacity=0.3,
            override=False,
        )
        painted_glass = res_glass["geometry"]
        self.assertEqual(painted_glass.material_name, "Glass")
        self.assertEqual(painted_glass.opacity, 0.3)
        self.assertEqual(len(painted_glass.face_materials), 6)
        self.assertEqual(painted_glass.face_materials[0], "Glass")
        self.assertEqual(painted_glass.face_opacities[0], 0.3)

        # 2. Assign Wood Frame
        box_wood = MeshData.create_box(Vec3(-0.1, -0.05, -0.1), 1.2, 0.2, 1.7)
        res_wood = mat_node.compute(
            geometry=box_wood,
            material="Wood Oak",
            name="",
            color_r=0.65,
            color_g=0.45,
            color_b=0.28,
            opacity=1.0,
            override=False,
        )
        painted_wood = res_wood["geometry"]
        self.assertEqual(painted_wood.material_name, "Wood Oak")
        self.assertEqual(painted_wood.opacity, 1.0)
        self.assertEqual(painted_wood.face_materials[0], "Wood Oak")

    def test_combine_parts_window_assembly(self):
        mat_cls = NODE_REGISTRY["mat.assign"]
        combine_cls = NODE_REGISTRY["mat.combine_parts"]

        mat_node = mat_cls()
        combine_node = combine_cls()

        glass = mat_node.compute(MeshData.create_box(Vec3(0, 0, 0), 1.0, 0.05, 1.2), "Glass", "", 0.7, 0.85, 0.95, 0.3, False)["geometry"]
        wood = mat_node.compute(MeshData.create_box(Vec3(-0.1, -0.05, -0.1), 1.2, 0.15, 1.4), "Wood Walnut", "", 0.38, 0.24, 0.16, 1.0, False)["geometry"]

        res = combine_node.compute(parts=[glass, wood], name="Window_01", ifc_class="IfcWindow")
        assembly = res["assembly"]
        self.assertEqual(assembly.name, "Window_01")
        self.assertEqual(assembly.ifc_class, "IfcWindow")
        # 6 faces for glass + 6 faces for wood = 12 faces
        self.assertEqual(len(assembly.faces), 12)
        # Verify first 6 faces are Glass (opacity 0.3) and last 6 are Wood Walnut (opacity 1.0)
        self.assertEqual(assembly.face_materials[:6], ["Glass"] * 6)
        self.assertEqual(assembly.face_opacities[:6], [0.3] * 6)
        self.assertEqual(assembly.face_materials[6:], ["Wood Walnut"] * 6)
        self.assertEqual(assembly.face_opacities[6:], [1.0] * 6)

    def test_boolean_toggle_interactive(self):
        toggle_cls = NODE_REGISTRY["input.toggle"]
        toggle = toggle_cls()
        self.assertTrue(toggle.param_values.get("val", True))
        self.assertEqual(toggle.compute(val=True)["out"], True)

        # Toggle value flips state
        toggle.toggle_value()
        self.assertFalse(toggle.param_values["val"])
        self.assertIn("FALSE", toggle.get_action_buttons()[0]["label"])
        self.assertIn("#c62828", toggle.get_action_buttons()[0]["color"])

        toggle.toggle_value()
        self.assertTrue(toggle.param_values["val"])
        self.assertIn("TRUE", toggle.get_action_buttons()[0]["label"])
        self.assertIn("#2e7d32", toggle.get_action_buttons()[0]["color"])

    def test_preview_shapes_without_output_node(self):
        engine = GraphEngine()
        circle = engine.add_node("curve.circle")
        box = engine.add_node("solid.box")

        # Evaluate WITHOUT any scene.output node on canvas
        engine.evaluate()
        meshes, points = engine.collect_preview_outputs()

        # Both the circle wire and box mesh must be visible in preview!
        self.assertGreaterEqual(len(meshes), 2)
        curve_wires = [m for m in meshes if len(m.edges) > 0 and len(m.faces) == 0]
        solid_meshes = [m for m in meshes if len(m.faces) > 0]
        self.assertGreater(len(curve_wires), 0, "Curve was not previewed without output node")
        self.assertGreater(len(solid_meshes), 0, "Solid was not previewed without output node")

        # Now add an output node and connect only the box to it
        out_node = engine.add_node("scene.output")
        engine.connect(box.id, "mesh", out_node.id, "mesh")
        engine.evaluate()

        # In preview: shapes are STILL visible (not hidden by output node)
        prev_meshes, _ = engine.collect_preview_outputs()
        self.assertGreaterEqual(len(prev_meshes), 2)

        # In bake: only the wired output node is collected!
        bake_meshes = engine.collect_bake_outputs()
        self.assertEqual(len(bake_meshes), 1)
        self.assertEqual(bake_meshes[0].faces, box.cached_outputs["mesh"].faces)

    def test_populate_mesh_with_face_materials(self):
        from __init__ import _populate_ingetrazo_mesh

        class MockFace:
            def __init__(self):
                self.attrs = {}

        class MockMesh:
            def __init__(self):
                self.faces = []
                self.edges = []
            def add_face(self, qvecs):
                f = MockFace()
                self.faces.append(f)
                return f
            def add_edge(self, p1, p2):
                self.edges.append((p1, p2))

        box = MeshData.create_box(Vec3(0, 0, 0), 1, 1, 1)
        box.face_materials = ["Glass"] * 3 + ["Wood Walnut"] * 3
        box.face_colors = [(0.7, 0.85, 0.95)] * 3 + [(0.38, 0.24, 0.16)] * 3
        box.face_opacities = [0.3] * 3 + [1.0] * 3

        mock_target = MockMesh()
        mock_scene = type("MockScene", (), {"materials": {}})()

        _populate_ingetrazo_mesh(mock_target, box, scene=mock_scene)
        self.assertEqual(len(mock_target.faces), 6)
        self.assertEqual(mock_target.faces[0].attrs["mat"], "Glass")
        self.assertEqual(mock_target.faces[0].attrs["opacity"], 0.3)
        self.assertEqual(mock_target.faces[3].attrs["mat"], "Wood Walnut")
        self.assertEqual(mock_target.faces[3].attrs["opacity"], 1.0)
        self.assertIn("Glass", mock_scene.materials)
        self.assertIn("Wood Walnut", mock_scene.materials)


class TestUIWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)
        discover_nodes(reload_modules=False)

    def test_ui_widget_instantiation(self):
        from ui_canvas import NodeEditorWidget
        engine = GraphEngine()
        widget = NodeEditorWidget(
            engine=engine,
            on_bake=lambda: None,
            on_live_toggled=lambda b: None,
        )
        self.assertIsNotNone(widget.scene)
        self.assertIsNotNone(widget.view)
        # Verify default preset loaded
        self.assertGreaterEqual(len(engine.nodes), 3)

    def test_node_item_buttons_and_bake(self):
        from ui_canvas import NodeEditorWidget
        from PySide6.QtWidgets import QPushButton
        engine = GraphEngine()
        baked_called = []
        widget = NodeEditorWidget(
            engine=engine,
            on_bake=lambda: baked_called.append(True),
            on_live_toggled=lambda b: None,
        )
        out_node = engine.add_node("scene.output", pos=(300, 100))
        widget.scene.rebuild_from_engine()

        node_item = widget.scene.node_items.get(out_node.id)
        self.assertIsNotNone(node_item)

        # Verify eye & power toggles
        self.assertTrue(out_node.is_enabled)
        node_item.toggle_enable()
        self.assertFalse(out_node.is_enabled)
        node_item.toggle_enable()
        self.assertTrue(out_node.is_enabled)

        self.assertTrue(out_node.is_preview_visible)
        node_item.toggle_preview()
        self.assertFalse(out_node.is_preview_visible)
        node_item.toggle_preview()
        self.assertTrue(out_node.is_preview_visible)

        # Verify bake button is rendered on the output node card
        self.assertIn("_btn_bake", node_item.proxies)
        bake_proxy = node_item.proxies["_btn_bake"]
        bake_btn = bake_proxy.widget()
        self.assertIn("Bake", bake_btn.text())

        # Click bake button
        bake_btn.click()
        self.assertEqual(len(baked_called), 1)


class TestNewNodesAndUIEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        discover_nodes(reload_modules=False)

    def test_heightmap_unequal_uv_and_normal(self):
        """Verify Resolution U != Resolution V generates correct grid without shearing, and normal points up."""
        img_node = NODE_REGISTRY["input.image_sampler"]()
        # 30 x 34 resolution
        res = img_node.compute(
            path="",
            size_x=10.0,
            size_y=12.0,
            min_z=0.0,
            max_z=2.0,
            count_u=30,
            count_v=34,
            invert=False,
            flip_normals=False,
        )
        mesh = res["mesh"]
        self.assertIsInstance(mesh, MeshData)
        self.assertEqual(len(mesh.vertices), 30 * 34)
        self.assertEqual(len(mesh.faces), 29 * 33)

        # Check face 0 vertices: (u=0, v=0), (u=1, v=0), (u=1, v=1), (u=0, v=1)
        f0 = mesh.faces[0]
        v0, v1, v2, v3 = [mesh.vertices[idx] for idx in f0]
        # x coordinates: v0.x < v1.x
        self.assertLess(v0[0], v1[0])
        # y coordinates: v0.y == v1.y and v2.y > v1.y
        self.assertAlmostEqual(v0[1], v1[1], places=3)
        self.assertGreater(v2[1], v1[1])

        # Verify normal points upward (+Z)
        p0, p1, p2, p3 = v0, v1, v2, v3
        nz = (
            (p0[0] - p1[0]) * (p0[1] + p1[1])
            + (p1[0] - p2[0]) * (p1[1] + p2[1])
            + (p2[0] - p3[0]) * (p2[1] + p3[1])
            + (p3[0] - p0[0]) * (p3[1] + p0[1])
        )
        self.assertGreater(nz, 0.0, "Face normal should point upward (+Z) for CCW winding")

    def test_plane_from_normal(self):
        """Verify PlaneFromNormalNode produces orthonormal basis and valid preview."""
        plane_cls = NODE_REGISTRY.get("vec.plane_normal")
        self.assertIsNotNone(plane_cls)
        plane_node = plane_cls()

        # Normal = (0, 0, 1)
        res = plane_node.compute(origin=Vec3(2, 3, 5), normal=Vec3(0, 0, 1), size=4.0)
        u = res["u_axis"]
        v = res["v_axis"]
        n = res["normal"]
        self.assertAlmostEqual(u.dot(v), 0.0, places=4)
        self.assertAlmostEqual(u.dot(n), 0.0, places=4)
        self.assertAlmostEqual(v.dot(n), 0.0, places=4)
        self.assertAlmostEqual(u.length(), 1.0, places=4)
        self.assertAlmostEqual(v.length(), 1.0, places=4)
        self.assertIsInstance(res["preview"], CurveData)
        self.assertEqual(len(res["preview"].points), 4)

        # Angled normal
        res_angled = plane_node.compute(origin=Vec3(0, 0, 0), normal=Vec3(1, 2, 3), size=2.0)
        ua = res_angled["u_axis"]
        va = res_angled["v_axis"]
        na = res_angled["normal"]
        self.assertAlmostEqual(ua.dot(va), 0.0, places=4)
        self.assertAlmostEqual(ua.dot(na), 0.0, places=4)
        self.assertAlmostEqual(va.dot(na), 0.0, places=4)

    def test_sweep_solid(self):
        """Verify SweepNode produces a watertight 3D solid with capped ends."""
        sweep_cls = NODE_REGISTRY.get("solid.sweep")
        self.assertIsNotNone(sweep_cls)
        sweep_node = sweep_cls()

        res = sweep_node.compute(profile=None, rail=None, capped=True, scale_end=1.5)
        solid = res["solid"]
        self.assertIsInstance(solid, MeshData)
        self.assertGreater(len(solid.vertices), 0)
        self.assertGreater(len(solid.faces), 0)

    def test_flip_normals(self):
        """Verify FlipNormalsNode inverts face vertex winding order and curve direction."""
        flip_cls = NODE_REGISTRY.get("mesh.flip_normals")
        self.assertIsNotNone(flip_cls)
        flip_node = flip_cls()

        # Test mesh flipping
        mesh = MeshData(
            vertices=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
            faces=[[0, 1, 2, 3]],
            name="TestQuad",
        )
        res = flip_node.compute(geometry=mesh)
        f_mesh = res["geometry"]
        self.assertEqual(f_mesh.faces[0], [3, 2, 1, 0])

        # Test curve flipping
        curve = CurveData(points=[Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(2, 0, 0)])
        res_c = flip_node.compute(geometry=curve)
        f_curve = res_c["geometry"]
        self.assertEqual(f_curve.points[0], Vec3(2, 0, 0))
        self.assertEqual(f_curve.points[2], Vec3(0, 0, 0))

    def test_panel_multiline_list_parsing(self):
        """Verify PanelNode parses multi-line numbers, vectors, and text into Grasshopper-style lists."""
        panel_cls = NODE_REGISTRY.get("input.panel")
        panel = panel_cls()

        # Numbers
        res_num = panel.compute(data=None, text="10\n20\n30\n40")
        self.assertEqual(res_num["out"], [10, 20, 30, 40])

        # Coordinates / Points
        res_pts = panel.compute(data=None, text="0, 0, 1\n5, 2, 3")
        self.assertEqual(len(res_pts["out"]), 2)
        self.assertEqual(res_pts["out"][0], Vec3(0, 0, 1))
        self.assertEqual(res_pts["out"][1], Vec3(5, 2, 3))

        # Data formatting when wired
        res_data = panel.compute(data=[12.5, 45.0, 99.0])
        self.assertIn("[0] 12.5", res_data["text"])
        self.assertIn("[1] 45", res_data["text"])
        self.assertIn("[2] 99", res_data["text"])

    def test_selective_preview_eye(self):
        """Verify geometry nodes show preview eye while non-geometry nodes do not."""
        from PySide6.QtWidgets import QApplication
        from ui_canvas import NodeItem
        app = QApplication.instance() or QApplication([])

        # Geometry node (Point XYZ produces VEC3)
        pt_node = NODE_REGISTRY["vec.point_xyz"]()
        pt_item = NodeItem(pt_node, on_param_changed=lambda a, b, c: None)
        self.assertTrue(pt_item.has_preview_eye)

        # Geometry node (Extrude produces MESH)
        ext_node = NODE_REGISTRY["solid.extrude"]()
        ext_item = NodeItem(ext_node, on_param_changed=lambda a, b, c: None)
        self.assertTrue(ext_item.has_preview_eye)

        # Non-geometry node (Math, Boolean Toggle, Number)
        math_node = NODE_REGISTRY["math.add"]()
        math_item = NodeItem(math_node, on_param_changed=lambda a, b, c: None)
        self.assertFalse(math_item.has_preview_eye)

        toggle_node = NODE_REGISTRY["input.toggle"]()
        toggle_item = NodeItem(toggle_node, on_param_changed=lambda a, b, c: None)
        self.assertFalse(toggle_item.has_preview_eye)

        num_node = NODE_REGISTRY["input.number"]()
        num_item = NodeItem(num_node, on_param_changed=lambda a, b, c: None)
        self.assertFalse(num_item.has_preview_eye)

    def test_painted_output_preview_and_bake(self):
        """Verify painted output preview displays in viewport and bakes with container material."""
        engine = GraphEngine()
        n_box = engine.add_node("solid.box")
        n_mat = engine.add_node("mat.assign")
        n_mat.set_param("material", "Wood Oak")
        n_out = engine.add_node("scene.output")
        n_out.set_param("group_name", "Oak_Table")

        engine.connect(n_box.id, "mesh", n_mat.id, "geometry")
        engine.connect(n_mat.id, "geometry", n_out.id, "mesh")

        # When mat.assign preview eye is muted, scene.output displays the painted geometry
        n_mat.is_preview_visible = False
        meshes, _ = engine.evaluate()
        self.assertGreaterEqual(len(meshes), 1)
        out_mesh = [m for m in meshes if m.name == "Oak_Table"][0]
        self.assertEqual(out_mesh.material_name, "Wood Oak")
        self.assertIsNotNone(out_mesh.color)

        # Bake output collects the painted mesh
        bake_meshes = engine.collect_bake_outputs()
        self.assertEqual(len(bake_meshes), 1)
        self.assertEqual(bake_meshes[0].material_name, "Wood Oak")
        self.assertEqual(bake_meshes[0].name, "Oak_Table")

    def test_inspector_custom_title_and_slider_configs(self):
        """Verify custom nickname/title and slider limits/decimals config and serialization."""
        engine = GraphEngine()
        n_box = engine.add_node("solid.box")
        app = QApplication.instance() or QApplication([])
        item_box = NodeItem(n_box, on_param_changed=lambda a, b, c: None)

        # Set custom title
        item_box.set_custom_title("Custom Column")
        self.assertEqual(n_box.custom_title, "Custom Column")

        # Update slider config (min, max, decimals, step)
        item_box.update_slider_config("dx", min_val=0.5, max_val=15.0, decimals=3, step=0.25)
        spec = [i for i in n_box.inputs if i.id == "dx"][0]
        self.assertEqual(spec.min_val, 0.5)
        self.assertEqual(spec.max_val, 15.0)
        self.assertEqual(spec.decimals, 3)
        self.assertEqual(spec.step, 0.25)

        # Serialize and deserialize via engine copy/paste
        data = engine.copy_nodes([n_box.id])
        new_nodes = engine.paste_nodes(data, offset=(20, 20))
        self.assertEqual(len(new_nodes), 1)
        pasted_box = new_nodes[0]
        self.assertEqual(pasted_box.custom_title, "Custom Column")
        pasted_spec = [i for i in pasted_box.inputs if i.id == "dx"][0]
        self.assertEqual(pasted_spec.min_val, 0.5)
        self.assertEqual(pasted_spec.max_val, 15.0)
        self.assertEqual(pasted_spec.decimals, 3)
        self.assertEqual(pasted_spec.step, 0.25)

    def test_flip_and_array_preview_eyes(self):
        """Verify Flip Normals, Linear Array, and Polar Array all display preview eye buttons."""
        app = QApplication.instance() or QApplication([])
        flip_node = NODE_REGISTRY["mesh.flip_normals"]()
        flip_item = NodeItem(flip_node, on_param_changed=lambda a, b, c: None)
        self.assertTrue(flip_item.has_preview_eye)

        arr_node = NODE_REGISTRY["xform.linear_array"]()
        arr_item = NodeItem(arr_node, on_param_changed=lambda a, b, c: None)
        self.assertTrue(arr_item.has_preview_eye)

        parr_node = NODE_REGISTRY["xform.polar_array"]()
        parr_item = NodeItem(parr_node, on_param_changed=lambda a, b, c: None)
        self.assertTrue(parr_item.has_preview_eye)

    def test_color_rgb_action_button(self):
        """Verify Color RGB node provides an action button to open color picker."""
        col_node = NODE_REGISTRY["mat.color_rgb"]()
        btns = col_node.get_action_buttons()
        self.assertEqual(len(btns), 1)
        self.assertEqual(btns[0]["action"], "pick_color")
        self.assertIn("Pick Color", btns[0]["label"])

    def test_pipe_solid_node(self):
        """Verify Pipe Solid node creates watertight meshes along open and closed curves with wall thickness."""
        self.assertIn("solid.pipe", NODE_REGISTRY)
        pipe_node = NODE_REGISTRY["solid.pipe"]()
        app = QApplication.instance() or QApplication([])
        item = NodeItem(pipe_node, on_param_changed=lambda a, b, c: None)
        self.assertTrue(item.has_preview_eye)

        # 1. Unwired fallback
        res_default = pipe_node.compute()
        mesh_default = res_default.get("solid")
        self.assertIsInstance(mesh_default, MeshData)
        self.assertGreater(len(mesh_default.vertices), 0)
        self.assertGreater(len(mesh_default.faces), 0)

        # 2. Straight line pipe with radius and caps
        c_line = CurveData(points=[Vec3(0, 0, 0), Vec3(0, 0, 4)], closed=False)
        res_line = pipe_node.compute(curve=c_line, radius=0.25, segments=16, capped=True)
        m_line = res_line["solid"]
        self.assertEqual(len(m_line.vertices), 32)
        self.assertEqual(len(m_line.faces), 18)  # 16 quads + 2 caps

        # Check watertightness
        edge_counts = {}
        for f in m_line.faces:
            for k in range(len(f)):
                e = (min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)]))
                edge_counts[e] = edge_counts.get(e, 0) + 1
        self.assertTrue(all(cnt == 2 for cnt in edge_counts.values()))

        # 3. Hollow tube with wall thickness
        res_tube = pipe_node.compute(curve=c_line, radius=0.25, thickness=0.05, segments=12, capped=True)
        m_tube = res_tube["solid"]
        self.assertEqual(len(m_tube.vertices), 48)  # 24 outer + 24 inner
        edge_counts_tube = {}
        for f in m_tube.faces:
            for k in range(len(f)):
                e = (min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)]))
                edge_counts_tube[e] = edge_counts_tube.get(e, 0) + 1
        self.assertTrue(all(cnt == 2 for cnt in edge_counts_tube.values()))

        # 4. Engine evaluation and badge text
        engine = GraphEngine()
        n_line = engine.add_node("curve.line")
        n_pipe = engine.add_node("solid.pipe")
        n_pipe.set_param("radius", 0.15)
        engine.connect(n_line.id, "curve", n_pipe.id, "curve")
        engine.evaluate()
        pipe_out = n_pipe.cached_outputs.get("solid")
        self.assertIsInstance(pipe_out, MeshData)
        self.assertIn("R: 0.15m", n_pipe.get_card_badge_text())

    def test_architectural_grid_node(self):
        """Verify Architectural Grid node generates axis curves, bubbles, and intersection points from spacings."""
        self.assertIn("arch.grid", NODE_REGISTRY)
        grid_node = NODE_REGISTRY["arch.grid"]()
        app = QApplication.instance() or QApplication([])
        item = NodeItem(grid_node, on_param_changed=lambda a, b, c: None)
        self.assertTrue(item.has_preview_eye)

        # 1. Default unwired computation
        res_default = grid_node.compute()
        self.assertEqual(len(res_default["x_coords"]), 4)  # 0, 6, 12, 18
        self.assertEqual(len(res_default["y_coords"]), 3)  # 0, 5, 10
        self.assertEqual(len(res_default["points"]), 12)   # 4 x 3
        self.assertEqual(len(res_default["x_lines"]), 4)
        self.assertEqual(len(res_default["y_lines"]), 3)
        self.assertGreater(len(res_default["bubbles"]), 0)
        grid_mesh = res_default["mesh"]
        self.assertIsInstance(grid_mesh, MeshData)
        self.assertEqual(grid_mesh.ifc_class, "IfcGrid")
        self.assertGreater(len(grid_mesh.edges), 0)

        # 2. Custom spacings list
        res_custom = grid_node.compute(
            x_spacings=[4.0, 5.0, 6.0],
            y_spacings=[6.0, 6.0],
            extension=2.0,
            bubble_radius=0.5,
            both_ends=True,
        )
        self.assertEqual(res_custom["x_coords"], [0.0, 4.0, 9.0, 15.0])
        self.assertEqual(res_custom["y_coords"], [0.0, 6.0, 12.0])
        self.assertEqual(len(res_custom["points"]), 12)
        # With both_ends=True: 4 top + 4 bottom + 3 left + 3 right = 14 bubbles
        self.assertEqual(len(res_custom["bubbles"]), 14)

        # 3. Graph Engine with Panel node wired to x_spacings
        engine = GraphEngine()
        panel = engine.add_node("input.panel")
        panel.set_param("text", "4.0\n5.0\n4.0")
        grid = engine.add_node("arch.grid")
        engine.connect(panel.id, "out", grid.id, "x_spacings")

        engine.evaluate()
        x_coords = grid.cached_outputs.get("x_coords")
        self.assertEqual(x_coords, [0.0, 4.0, 9.0, 13.0])
        self.assertIn("Axes", grid.get_card_badge_text())

    def test_locked_node_sends_no_data(self):
        """Verify that when a node is locked/disabled, it sends no data and downstream nodes do not evaluate."""
        engine = GraphEngine()
        panel = engine.add_node("input.panel")
        panel.set_param("text", "4.0\n5.0\n6.0")
        grid = engine.add_node("arch.grid")
        engine.connect(panel.id, "out", grid.id, "x_spacings")

        # Active evaluation
        meshes, _ = engine.evaluate()
        self.assertGreater(len(meshes), 0)
        self.assertIsNotNone(grid.cached_outputs.get("x_coords"))

        # Lock / disable the panel
        panel.is_enabled = False
        engine.mark_dirty(panel.id)
        meshes_disabled, _ = engine.evaluate()

        # Grid receives no data, so it outputs None and produces 0 meshes
        self.assertIsNone(panel.cached_outputs.get("out"))
        self.assertIsNone(grid.cached_outputs.get("x_coords"))
        self.assertEqual(len(meshes_disabled), 0)

        # Re-enable the panel
        panel.is_enabled = True
        engine.mark_dirty(panel.id)
        meshes_re_enabled, _ = engine.evaluate()
        self.assertGreater(len(meshes_re_enabled), 0)
        self.assertEqual(grid.cached_outputs.get("x_coords"), [0.0, 4.0, 9.0, 15.0])

    def test_roof_straight_skeleton_only(self):
        """Verify roof node has no dropdown style choices and generates straight skeleton hip roof."""
        roof_cls = NODE_REGISTRY["arch.roof"]
        input_ids = [inp.id for inp in roof_cls.inputs]
        self.assertNotIn("style", input_ids)

        roof = roof_cls()
        boundary = [Vec3(0, 0, 0), Vec3(10, 0, 0), Vec3(10, 6, 0), Vec3(0, 6, 0)]
        c_boundary = CurveData(points=boundary, closed=True)
        res = roof.compute(boundary=c_boundary, pitch=30.0, overhang=0.5, thickness=0.2)
        mesh = res.get("solid")
        self.assertIsInstance(mesh, MeshData)
        self.assertGreater(len(mesh.vertices), 0)
        self.assertGreater(len(mesh.faces), 0)

    def test_panel_single_output_and_checkbox_style(self):
        """Verify panel node has single output pin and checkbox has indicator outline styling."""
        panel_cls = NODE_REGISTRY["input.panel"]
        self.assertEqual(len(panel_cls.outputs), 1)
        self.assertEqual(panel_cls.outputs[0].id, "out")
        self.assertEqual(panel_cls.outputs[0].label, "Output")

        app = QApplication.instance() or QApplication([])
        panel_node = panel_cls()
        panel_item = NodeItem(panel_node, on_param_changed=lambda a, b, c: None)
        self.assertIn("out", panel_item.output_sockets)

        # Check toggle / boolean checkbox on architectural grid
        grid_node = NODE_REGISTRY["arch.grid"]
        grid_item = NodeItem(grid_node(), on_param_changed=lambda a, b, c: None)
        proxy = grid_item.proxies.get("both_ends")
        self.assertIsNotNone(proxy)
        w = proxy.widget()
        from PySide6.QtWidgets import QCheckBox
        self.assertIsInstance(w, QCheckBox)
        self.assertIn("QCheckBox::indicator", w.styleSheet())
        self.assertIn("border:", w.styleSheet())



if __name__ == "__main__":
    unittest.main()
