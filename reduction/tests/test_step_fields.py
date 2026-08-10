from django.test import SimpleTestCase

from reduction.step_fields import discover_step_templates, get_step_fields


class DiscoverStepTemplatesTests(SimpleTestCase):
    def test_finds_known_processors(self):
        templates = discover_step_templates()
        self.assertIn("pyobs.images.processors.image.Flip", templates)
        self.assertIn("pyobs.images.processors.calibration.Calibration", templates)
        self.assertIn("pyobs.images.processors.detection.SepSourceDetection", templates)

    def test_excludes_abstract_base_classes(self):
        templates = discover_step_templates()
        # SourceDetection, Astrometry, Offsets, Photometry, ExpTimeEstimator are abstract
        # bases meant to be subclassed further, not steps to add directly.
        for base_name in ("SourceDetection", "Offsets", "Photometry", "ExpTimeEstimator"):
            self.assertNotIn(base_name, [t.rsplit(".", 1)[-1] for t in templates])

    def test_is_sorted_and_has_no_duplicates(self):
        templates = discover_step_templates()
        self.assertEqual(templates, sorted(set(templates)))
        self.assertGreater(len(templates), 20)  # sanity floor, not an exact count

    def test_every_discovered_template_is_introspectable(self):
        """Every path discover_step_templates() offers in the "Add step" dropdown must
        actually work when the builder introspects it -- a class discover_step_templates()
        finds but get_step_fields() can't handle would be an entry that breaks the page."""
        for path in discover_step_templates():
            with self.subTest(path=path):
                fields = get_step_fields(path)
                self.assertIsInstance(fields, list)


class GetStepFieldsTests(SimpleTestCase):
    def test_archive_field_is_hidden(self):
        """archive is auto-filled from the site's own config (see pyobs-core's
        PipelineMixin), not something an operator sets per step -- see
        reduction/tasks.py's build_reduction_config, which never writes an "archive" key
        into a step's config."""
        fields = get_step_fields("pyobs.images.processors.calibration.Calibration")
        self.assertNotIn("archive", [f["name"] for f in fields])

    def test_on_error_appears_for_a_class_that_only_inherits_it(self):
        """Flip's own __init__ doesn't redeclare on_error -- it's only reachable via the
        **kwargs it forwards up to ImageProcessor.__init__. inspect.signature(Flip.__init__)
        alone would miss it entirely; get_step_fields must merge it in."""
        fields = {f["name"]: f for f in get_step_fields("pyobs.images.processors.image.Flip")}
        self.assertIn("on_error", fields)
        self.assertEqual(fields["on_error"]["type"], "choices")
        self.assertEqual(sorted(fields["on_error"]["choices"]), ["error", "ignore", "info", "raise"])

    def test_on_error_default_is_overridden_to_error(self):
        """Builder-only default -- pyobs-core's own ImageProcessor default is "raise";
        a freshly-added step here pre-selects "error" instead, so a failing step gets
        marked/logged rather than aborting the whole run by default. A step only
        actually gets on_error="error" if it's saved with that value still selected."""
        fields = {f["name"]: f for f in get_step_fields("pyobs.images.processors.image.Flip")}
        self.assertEqual(fields["on_error"]["default"], "error")

    def test_on_error_not_duplicated_for_a_class_that_redeclares_it(self):
        """AstrometryDotNet explicitly redeclares on_error in its own __init__ -- the
        merge must not clobber or duplicate that."""
        fields = [f for f in get_step_fields("pyobs.images.processors.astrometry.AstrometryDotNet") if f["name"] == "on_error"]
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["type"], "choices")
