"""Schema, approval-gate and catalogue tests for the two-arm architecture.

Everything here is offline. Synthetic fixtures are used for the failure paths so
that the real definition files are never mutated.
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = PROJECT_ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from src.chapter3.catalog import (  # noqa: E402
    CANONICAL_QUALIFIER,
    FORBIDDEN_QUALIFIERS,
    LABEL_ORDERS,
    PROTECTION_SENTENCE,
    RECONSTRUCTED_PROVENANCE,
    SUPERSEDED_QUALIFIERS,
    AnchorInconsistency,
    ApprovalBlocked,
    ApprovalInconsistency,
    FrozenArtifact,
    HashMismatch,
    QualifierInconsistency,
    SchemaError,
    approval_gates,
    build_catalog,
    load_json,
    render_system_prompt,
    require_approved,
    selectable_templates,
    validate_camuffo_prompts,
    validate_carlson_prompts,
    validate_labels,
    validate_rubric,
    verify_anchor_consistency,
    verify_approval_consistency,
    verify_label_order_equivalence,
    verify_qualifier_consistency,
    verify_reference_hashes,
    write_jsonl,
)
from src.chapter3.design import sha256_bytes  # noqa: E402
from src.chapter3.results import parse_binary_label  # noqa: E402


CONFIG = PROJECT_ROOT / "config"
EXPERIMENT_PATH = CONFIG / "experiments" / "chapter3_comparative_experiment_v1.json"
RUBRIC_PATH = CONFIG / "rubrics" / "societal_benefit_v1.json"
LABELS_PATH = CONFIG / "labels" / "societal_benefit_labels_v1.json"
CARLSON_PATH = CONFIG / "prompts" / "carlson_table3_v1.json"
CAMUFFO_PATH = CONFIG / "prompts" / "camuffo_societal_benefit_P3_v1.json"


def deep_copy(value):
    return json.loads(json.dumps(value))


class RubricTests(unittest.TestCase):
    def setUp(self):
        self.rubric = load_json(RUBRIC_PATH)

    def test_real_rubric_validates(self):
        validate_rubric(self.rubric)

    def test_construct_and_unit_are_recorded(self):
        self.assertEqual(
            self.rubric["construct"],
            "broader societal benefit of the main product or service",
        )
        self.assertIn("main product or service", self.rubric["unit_of_evaluation"]["scope"])

    def test_the_rubric_is_a_reconstruction_not_the_human_codebook(self):
        """A reader who assumes otherwise misreads every disagreement."""

        self.assertEqual(self.rubric["provenance_status"], RECONSTRUCTED_PROVENANCE)
        self.assertFalse(self.rubric["original_human_codebook_available"])
        note = self.rubric["provenance_note"]
        self.assertEqual(len(note["published_by_the_paper"]), 4)
        published = " ".join(note["published_by_the_paper"])
        self.assertIn("consumer-only", published)
        self.assertIn("main product or service", published)
        self.assertIn("Table 3", published)
        withheld = " ".join(note["not_published_by_the_paper"])
        self.assertIn("codebook", withheld)
        self.assertIn("instructions given to the human coders", withheld)
        self.assertIn("reconstruction difference", note["consequence"])

    def test_an_undeclared_provenance_is_rejected(self):
        broken = deep_copy(self.rubric)
        broken["original_human_codebook_available"] = True
        with self.assertRaisesRegex(SchemaError, "original_human_codebook_available"):
            validate_rubric(broken)

    def test_insufficient_information_resolves_to_zero(self):
        rule = next(
            entry["rule"]
            for entry in self.rubric["operational_rules"]
            if entry["id"] == "insufficient_information"
        )
        self.assertIn("0", rule)

    def test_the_file_is_approved_content_and_representation(self):
        self.assertEqual(self.rubric["status"], "approved")
        state = self.rubric["approval_state"]
        self.assertEqual(state["substantive_decisions"], "researcher_approved")
        self.assertEqual(state["json_representation"], "researcher_approved")

    def test_the_scope_exclusion_does_not_rule_out_prospective_offerings(self):
        """A Kickstarter campaign is necessarily prospective."""

        unit = self.rubric["unit_of_evaluation"]
        self.assertNotIn("the venture's future plans", unit["excludes"])
        self.assertIn("ancillary to the main offering", unit["excludes"])
        self.assertIn("commitments or initiatives", unit["excludes"])
        self.assertIn("whether current or planned", unit["includes"])

    def test_the_ten_operational_rules_are_recorded(self):
        ids = {rule["id"] for rule in self.rubric["operational_rules"]}
        self.assertEqual(
            ids,
            {
                "main_offering_only",
                "integral_processes_only",
                "concrete_mechanism_required",
                "direct_users_do_not_disqualify",
                "generic_language_insufficient",
                "intentions_and_donations_insufficient",
                "fair_trade_and_labour",
                "insufficient_information",
                "no_success_forecasting",
                "no_realised_impact_required",
            },
        )

    def test_the_withdrawn_rules_are_not_operational(self):
        """Drafted then withdrawn: audit trail only, never sent to a model."""

        removed = self.rubric["removed_rules"]
        self.assertEqual(removed["status"], "non_operational")
        self.assertEqual(
            set(removed["rules"]),
            {
                "health_products",
                "price_and_convenience",
                "cultural_products",
                "job_creation_and_growth",
            },
        )
        operational = {rule["id"] for rule in self.rubric["operational_rules"]}
        self.assertEqual(operational & set(removed["rules"]), set())

    def test_a_withdrawn_rule_cannot_also_be_operational(self):
        broken = deep_copy(self.rubric)
        broken["operational_rules"].append(
            {"id": "cultural_products", "rule": "Cultural products are 0."}
        )
        with self.assertRaisesRegex(SchemaError, "must not also be operational"):
            validate_rubric(broken)

    def test_direct_users_do_not_disqualify_a_societal_benefit(self):
        rule = next(
            r for r in self.rubric["operational_rules"]
            if r["id"] == "direct_users_do_not_disqualify"
        )
        self.assertIn("even when it reaches direct users", rule["rule"])

    def test_generic_language_alone_never_qualifies(self):
        rules = {r["id"]: r["rule"] for r in self.rubric["operational_rules"]}
        self.assertIn("green", rules["generic_language_insufficient"])
        self.assertIn("sustainable", rules["generic_language_insufficient"])
        self.assertIn("donations", rules["intentions_and_donations_insufficient"])

    def test_anchors_come_from_the_paper_not_from_the_human_labels(self):
        anchors = self.rubric["anchors"]
        self.assertEqual(anchors["status"], "illustrative_not_exhaustive")
        provenance = anchors["provenance"]
        self.assertIn("Table 3", provenance["source"])
        self.assertEqual(provenance["file"], "docs/sources/carlson_burbano_2026.pdf")
        self.assertEqual(len(provenance["file_sha256"]), 64)
        self.assertIn("NOT derived from inspecting the human labels", provenance["note"])

    def test_the_three_anchors_match_table_3(self):
        by_text = {a["text"]: a for a in self.rubric["anchors"]["examples"]}
        self.assertEqual(by_text["Solar-powered water purifier for communities"]["label"], 1)
        self.assertEqual(by_text["Educational coding app for children"]["label"], 1)
        self.assertEqual(by_text["Premium leather accessories"]["label"], 0)
        self.assertEqual(
            by_text["Premium leather accessories"]["published_reason"],
            "the benefit is consumer-only",
        )

    def test_a_rubric_without_its_operational_rules_is_rejected(self):
        broken = deep_copy(self.rubric)
        broken["operational_rules"] = broken["operational_rules"][:3]
        with self.assertRaisesRegex(SchemaError, "operational_rules"):
            validate_rubric(broken)

    def test_an_unmarked_anchor_set_is_rejected(self):
        broken = deep_copy(self.rubric)
        broken["anchors"]["status"] = "definitive"
        with self.assertRaisesRegex(SchemaError, "illustrative_not_exhaustive"):
            validate_rubric(broken)

    def test_duplicate_rule_ids_are_rejected(self):
        broken = deep_copy(self.rubric)
        broken["operational_rules"].append(dict(broken["operational_rules"][0]))
        with self.assertRaisesRegex(SchemaError, "unique"):
            validate_rubric(broken)

    def test_empty_assign_0_list_is_rejected(self):
        broken = deep_copy(self.rubric)
        broken["assign_0_when"] = []
        with self.assertRaises(SchemaError):
            validate_rubric(broken)


class LabelContractTests(unittest.TestCase):
    def setUp(self):
        self.labels = load_json(LABELS_PATH)

    def test_real_label_set_validates(self):
        validate_labels(self.labels)

    def test_contract_matches_the_parser_exactly(self):
        """Every documented example must behave as the parser behaves."""

        contract = self.labels["output_contract"]
        for accepted in contract["accepted_examples"]:
            with self.subTest(value=accepted):
                self.assertIn(parse_binary_label(accepted), (0, 1))
        for rejected in contract["rejected_examples"]:
            with self.subTest(value=rejected):
                with self.assertRaises(ValueError):
                    parse_binary_label(rejected)

    def test_whitespace_only_stripping_is_documented(self):
        contract = self.labels["output_contract"]
        self.assertEqual(contract["accepted_after_strip"], ["0", "1"])
        for value in ("0 ", " 1", "1\n"):
            self.assertIn(value, contract["accepted_examples"])

    def test_parse_error_never_becomes_a_class(self):
        violation = self.labels["output_contract"]["on_violation"]
        self.assertEqual(violation["status"], "parse_error")
        self.assertIsNone(violation["parsed_label"])
        with self.assertRaises(SchemaError):
            broken = deep_copy(self.labels)
            broken["output_contract"]["on_violation"]["parsed_label"] = 0
            validate_labels(broken)

    def test_the_file_is_approved_content_and_representation(self):
        self.assertEqual(self.labels["status"], "approved")
        state = self.labels["approval_state"]
        self.assertEqual(state["substantive_decisions"], "researcher_approved")
        self.assertEqual(state["json_representation"], "researcher_approved")

    def test_only_success_bears_a_sample(self):
        self.assertEqual(
            self.labels["retry_policy_contract"]["sample_bearing_statuses"], ["success"]
        )

    def test_a_parse_error_is_not_a_technical_failure(self):
        kinds = {
            kind["id"]: kind
            for kind in self.labels["retry_policy_contract"]["failure_kinds"]
        }
        self.assertEqual(set(kinds), {"technical_failure", "parse_error"})

        technical = kinds["technical_failure"]
        self.assertTrue(technical["automatic_retry"])
        self.assertFalse(technical["slot_consumed"])
        self.assertIn("no completion was received", technical["definition"])

        parse_error = kinds["parse_error"]
        self.assertFalse(parse_error["automatic_retry"])
        self.assertTrue(parse_error["slot_consumed"])
        self.assertFalse(parse_error["yields_valid_label"])
        self.assertIn("preserve the original output", parse_error["retry_rule"])

    def test_the_parse_error_rule_records_why_retrying_would_bias(self):
        parse_error = next(
            kind
            for kind in self.labels["retry_policy_contract"]["failure_kinds"]
            if kind["id"] == "parse_error"
        )
        self.assertIn("condition the realised sample", parse_error["rationale"])
        forbidden = " ".join(parse_error["forbidden"]).lower()
        self.assertIn("retrying a parse_error automatically", forbidden)
        self.assertIn("replacing the missing sample", forbidden)

    def test_a_parse_error_consumes_its_slot(self):
        contract = self.labels["retry_policy_contract"]
        self.assertEqual(contract["slot_consuming_statuses"], ["success", "parse_error"])
        self.assertIn(
            "never automatically refilled",
            next(k for k in contract["failure_kinds"] if k["id"] == "parse_error")["slot_note"],
        )

    def test_remediation_is_not_implemented_and_stays_out_of_the_primary_analysis(self):
        remediation = self.labels["retry_policy_contract"]["remediation"]
        self.assertEqual(remediation["status"], "not_implemented")
        requirements = " ".join(remediation["requirements"])
        self.assertIn("preserve the original output", requirements)
        self.assertIn("explicitly marked", requirements)
        self.assertIn("excluded from the primary analysis", requirements)

    def test_an_automatically_retried_parse_error_is_rejected(self):
        broken = deep_copy(self.labels)
        for kind in broken["retry_policy_contract"]["failure_kinds"]:
            if kind["id"] == "parse_error":
                kind["automatic_retry"] = True
        with self.assertRaisesRegex(SchemaError, "never be retried automatically"):
            validate_labels(broken)

    def test_a_parse_error_that_frees_its_slot_is_rejected(self):
        broken = deep_copy(self.labels)
        broken["retry_policy_contract"]["slot_consuming_statuses"] = ["success"]
        with self.assertRaisesRegex(SchemaError, "consume its sample slot"):
            validate_labels(broken)

    def test_collapsing_the_two_failure_kinds_is_rejected(self):
        broken = deep_copy(self.labels)
        broken["retry_policy_contract"]["failure_kinds"] = [
            kind
            for kind in broken["retry_policy_contract"]["failure_kinds"]
            if kind["id"] != "parse_error"
        ]
        with self.assertRaisesRegex(SchemaError, "distinguish technical_failure"):
            validate_labels(broken)

    def test_unreported_reasoning_tokens_are_null_not_zero(self):
        reporting = self.labels["reasoning_contract"]["reasoning_tokens_reporting"]
        self.assertIn("null", reporting["when_absent"])
        self.assertIn("false", reporting["when_absent"])
        self.assertIn("Never assume", reporting["rule"])


class CarlsonPromptTests(unittest.TestCase):
    def setUp(self):
        self.prompts = load_json(CARLSON_PATH)

    def test_real_set_validates(self):
        validate_carlson_prompts(self.prompts)

    def test_seven_canonical_strategies_with_paper_names(self):
        names = [entry["strategy_name"] for entry in self.prompts["prompts"]]
        self.assertEqual(len(names), 7)
        self.assertIn("Reflection on Search Trees (RoT)", names)
        self.assertNotIn("Rule of Thought", " ".join(names))

    def test_source_records_file_page_and_hash(self):
        source = self.prompts["source"]
        self.assertEqual(source["file"], "docs/sources/carlson_burbano_2026.pdf")
        self.assertEqual(source["table_page"], 13)
        self.assertEqual(len(source["file_sha256"]), 64)

    def test_every_prompt_ends_with_the_output_instruction(self):
        for entry in self.prompts["prompts"]:
            with self.subTest(template=entry["template_id"]):
                self.assertTrue(entry["text"].endswith("Here is the text:"))
                self.assertNotIn("(0 or 1)", entry["text"])

    def test_few_shot_preserves_curly_quotation_marks(self):
        text = next(
            e["text"] for e in self.prompts["prompts"] if e["strategy_id"] == "few_shot"
        )
        self.assertEqual(text.count("“"), 3)
        self.assertEqual(text.count("”"), 3)
        self.assertNotIn('"', text)

    def test_apostrophes_are_straight_as_verified(self):
        for strategy in ("role_based", "tot", "rot"):
            text = next(
                e["text"] for e in self.prompts["prompts"] if e["strategy_id"] == strategy
            )
            with self.subTest(strategy=strategy):
                self.assertIn("campaign's", text)
                self.assertNotIn("’", text)

    def test_zero_shot_closing_differs_from_the_other_six(self):
        texts = {e["strategy_id"]: e["text"] for e in self.prompts["prompts"]}
        self.assertTrue(texts["zero_shot"].endswith("1 for yes, 0 for no. Here is the text:"))
        for strategy, text in texts.items():
            if strategy != "zero_shot":
                with self.subTest(strategy=strategy):
                    self.assertTrue(text.endswith("Answer only with a number. Here is the text:"))

    def test_visual_verification_is_recorded_as_closed(self):
        self.assertEqual(self.prompts["approval_status"], "approved")
        self.assertEqual(
            self.prompts["approval_basis"], "visual_verification_of_table_3_by_researcher"
        )
        transcription = self.prompts["transcription"]
        self.assertEqual(
            transcription["status"], "visually_verified_normalised_unicode_transcription"
        )
        for change in transcription["normalised"]:
            with self.subTest(change=change["change"]):
                self.assertFalse(change["needs_researcher_confirmation"])
                self.assertTrue(change["confirmed_as_artefact_by_researcher"])

    def test_the_file_does_not_claim_to_be_the_original_bytes(self):
        """A normalised transcription must not be presented as the source bytes."""

        transcription = self.prompts["transcription"]
        self.assertFalse(transcription["is_original_binary_representation"])
        note = self.prompts["representation_note"]
        self.assertIn("NORMALISED UNICODE TRANSCRIPTION", note)
        self.assertIn("not the original binary representation", note)

    def test_the_two_line_wrap_artefacts_are_documented(self):
        changes = " ".join(c["change"] for c in self.prompts["transcription"]["normalised"])
        self.assertIn("consumer-only", changes)
        self.assertIn("environmental/social/economic", changes)

    def test_rejoined_words_appear_unsplit_in_the_stored_text(self):
        texts = {e["strategy_id"]: e["text"] for e in self.prompts["prompts"]}
        self.assertIn("consumer-only benefit", texts["few_shot"])
        self.assertNotIn("consumer- only", texts["few_shot"])
        self.assertIn("environmental/social/economic", texts["tot"])
        self.assertNotIn("environmental/social/ economic", texts["tot"])

    def test_no_stored_text_carries_the_extraction_artefacts(self):
        for entry in self.prompts["prompts"]:
            with self.subTest(template=entry["template_id"]):
                self.assertNotIn(" :", entry["text"])
                self.assertNotIn(" ”", entry["text"])
                self.assertNotIn("  ", entry["text"])

    def test_truncated_csv_variant_is_recorded_as_corrupted(self):
        excluded = self.prompts["excluded_sources"]
        corrupted = [e for e in excluded if e.get("canonical_status") == "corrupted"]
        self.assertEqual(len(corrupted), 1)
        self.assertFalse(corrupted[0]["selectable"])

    def test_csv_is_recorded_as_a_subset_not_the_published_set(self):
        note = next(
            e["coverage_note"] for e in self.prompts["excluded_sources"] if "coverage_note" in e
        )
        self.assertIn("100", note)
        self.assertIn("50", note)

    def test_local_template_naming_error_is_recorded(self):
        note = self.prompts["naming_note"]
        self.assertIn("Reasoning with competing arguments", note["issue"])
        self.assertIn("Reflection on Search Trees", note["correction"])

    def test_six_strategies_is_rejected(self):
        broken = deep_copy(self.prompts)
        broken["prompts"] = broken["prompts"][:6]
        with self.assertRaisesRegex(SchemaError, "seven"):
            validate_carlson_prompts(broken)

    def test_a_derived_variation_is_rejected(self):
        broken = deep_copy(self.prompts)
        broken["prompts"][0]["canonical_status"] = "derived_variation"
        with self.assertRaisesRegex(SchemaError, "canonical_table3"):
            validate_carlson_prompts(broken)


class CamuffoPromptTests(unittest.TestCase):
    def setUp(self):
        self.prompts = load_json(CAMUFFO_PATH)
        self.renderings = {
            order: render_system_prompt(self.prompts, order) for order in LABEL_ORDERS
        }
        self.system = self.renderings["10"]

    def test_real_set_validates_structurally(self):
        validate_camuffo_prompts(self.prompts)

    def test_the_two_renderings_differ_only_inside_the_label_block(self):
        """The whole counterbalancing claim rests on this."""

        verify_label_order_equivalence(self.prompts)
        prefix, suffix = self.prompts["system_prompt"]["template"].split("[LABEL_RULES]")
        for order, rendered in self.renderings.items():
            with self.subTest(order=order):
                self.assertTrue(rendered.startswith(prefix))
                self.assertTrue(rendered.endswith(suffix))
        self.assertNotEqual(self.renderings["10"], self.renderings["01"])

    def test_the_two_blocks_carry_the_same_rules(self):
        blocks = self.prompts["system_prompt"]["label_rules"]
        for sentence in self.prompts["system_prompt"]["equivalence"]["identical_sentences"]:
            for order in LABEL_ORDERS:
                with self.subTest(order=order, sentence=sentence[:40]):
                    self.assertIn(sentence, blocks[order])

    def test_the_presentation_order_actually_differs(self):
        blocks = self.prompts["system_prompt"]["label_rules"]
        self.assertTrue(blocks["10"].startswith("Assign 1"))
        self.assertTrue(blocks["01"].startswith("Assign 0"))
        self.assertLess(blocks["10"].index("Assign 1"), blocks["10"].index("Assign 0"))
        self.assertLess(blocks["01"].index("Assign 0"), blocks["01"].index("Assign 1"))

    def test_the_mapping_never_changes_with_the_order(self):
        """Two serialisations of one prompt, not two rubrics."""

        mapping = self.prompts["system_prompt"]["mapping_invariant"]
        self.assertEqual(mapping["1"], "qualifying societal benefit")
        self.assertEqual(mapping["0"], "no qualifying benefit, or insufficient information")
        for order, block in self.prompts["system_prompt"]["label_rules"].items():
            with self.subTest(order=order):
                self.assertIn(
                    "1 means that the main product or service presents"
                    if order == "10"
                    else "1 means that it does",
                    block,
                )

    def test_an_inverted_mapping_is_rejected(self):
        broken = deep_copy(self.prompts)
        broken["system_prompt"]["label_rules"]["01"] = broken["system_prompt"]["label_rules"][
            "01"
        ].replace("Assign 0 when", "Assign 9 when")
        with self.assertRaisesRegex(SchemaError, "state the 0 rule first"):
            validate_camuffo_prompts(broken)

    def test_identical_blocks_are_rejected(self):
        broken = deep_copy(self.prompts)
        broken["system_prompt"]["label_rules"]["01"] = broken["system_prompt"]["label_rules"]["10"]
        with self.assertRaises(SchemaError):
            validate_camuffo_prompts(broken)

    def test_an_unknown_label_order_is_refused(self):
        with self.assertRaisesRegex(SchemaError, "Unknown label_order"):
            render_system_prompt(self.prompts, "11")

    def test_counterbalancing_is_scoped_to_this_arm(self):
        counterbalancing = self.prompts["counterbalancing"]
        self.assertEqual(counterbalancing["scope"], "camuffo_arm_only")
        self.assertIn("never reordered", counterbalancing["carlson_note"])
        self.assertIn(
            "Only the order in which the two label rules are presented is varied",
            counterbalancing["randomisation_is_presentation_only"],
        )

    def test_the_one_token_cap_is_proposed_not_settled(self):
        assembly = self.prompts["assembly"]
        self.assertEqual(assembly["max_output_tokens"], 1)
        self.assertEqual(assembly["max_output_tokens_status"], "approved_pending_smoke_validation")
        self.assertIn("not a semantic guarantee", assembly["max_output_tokens_note"])
        self.assertIn("finish_reason", assembly["max_output_tokens_note"])

    def test_the_arm_is_not_called_a_literal_replication(self):
        self.assertEqual(
            self.prompts["design_label"],
            "feasibility-adapted Camuffo-type variance-aware design",
        )
        self.assertIn("NOT a literal replication", self.prompts["design_label_note"])

    def test_the_set_is_approved(self):
        self.assertEqual(self.prompts["approval_status"], "approved")
        self.assertEqual(self.prompts["approved_by"], "researcher")

    def test_three_variants_one_base_two_paraphrases(self):
        roles = [v["role"] for v in self.prompts["variants"]]
        self.assertEqual(roles.count("base"), 1)
        self.assertEqual(roles.count("paraphrase"), 2)

    def test_design_is_three_by_three_by_three(self):
        design = self.prompts["design"]
        self.assertEqual((design["P"], design["S"], design["M"]), (3, 3, 3))

    def test_all_levels_odd_so_no_tie_is_possible(self):
        design = self.prompts["design"]
        for key in ("P", "S", "M"):
            with self.subTest(level=key):
                self.assertEqual(design[key] % 2, 1)

    def test_both_renderings_carry_the_invariants(self):
        for order, system in self.renderings.items():
            for token in ("main product or service", "Assign 1", "Assign 0", "0 or 1"):
                with self.subTest(order=order, token=token):
                    self.assertIn(token, system)

    def test_questions_differ_only_at_the_surface(self):
        questions = [v["question"] for v in self.prompts["variants"]]
        self.assertEqual(len(set(questions)), 3)
        for question in questions:
            with self.subTest(question=question):
                self.assertIn("main product or service", question)
                self.assertIn("campaign text below", question)
                self.assertIn("substantive", question)
                self.assertRegex(question, r"societ(y|al)")
                self.assertIn("consumer", question)

    def test_the_consumer_exclusion_wording_is_absent(self):
        """Ruled out as narrower than the construct.

        It would exclude educational, health and accessibility benefits that
        also reach the direct users; the paper's own Few-Shot example treats an
        educational app for children as a positive case.
        """

        forbidden = self.prompts["forbidden_expressions"]["expressions"]
        self.assertIn("beyond its direct consumers", forbidden)
        for expression in forbidden:
            for variant in self.prompts["variants"]:
                with self.subTest(variant=variant["variant_id"], expression=expression):
                    self.assertNotIn(expression, variant["question"])
            for order, system in self.renderings.items():
                with self.subTest(order=order, expression=expression):
                    self.assertNotIn(expression, system)

    def test_the_operative_qualifier_is_used_in_both_renderings(self):
        for order, system in self.renderings.items():
            with self.subTest(order=order):
                self.assertIn(CANONICAL_QUALIFIER, system)

    def test_the_superseded_wording_is_gone(self):
        for wording in SUPERSEDED_QUALIFIERS:
            for order, system in self.renderings.items():
                with self.subTest(wording=wording, order=order):
                    self.assertNotIn(wording, system)

    def test_the_campaign_text_is_marked_as_content_not_instructions(self):
        """Campaign descriptions are untrusted third-party text."""

        for order, system in self.renderings.items():
            with self.subTest(order=order):
                self.assertIn(PROTECTION_SENTENCE, system)

    def test_the_delimiter_is_shared_and_named_in_both_renderings(self):
        delimiter = self.prompts["assembly"]["delimiter"]
        self.assertTrue(delimiter["shared_across_variants"])
        self.assertNotEqual(delimiter["open"], delimiter["close"])
        for mark in (delimiter["open"], delimiter["close"]):
            for order, system in self.renderings.items():
                with self.subTest(mark=mark, order=order):
                    self.assertIn(mark, system)

    def test_no_variant_carries_its_own_delimiter(self):
        """Delimiter and text position are shared, so they are not part of P."""

        delimiter = self.prompts["assembly"]["delimiter"]
        for variant in self.prompts["variants"]:
            with self.subTest(variant=variant["variant_id"]):
                self.assertNotIn(delimiter["open"], variant["question"])
                self.assertNotIn(delimiter["close"], variant["question"])
        self.assertEqual(
            {row["dimension"] for row in self.prompts["equivalence_table"] if row["invariant"]}
            & {"campaign-text delimiter", "position of the campaign text", "anchors"},
            {"campaign-text delimiter", "position of the campaign text", "anchors"},
        )

    def test_the_anchors_are_shared_not_per_variant(self):
        anchors = self.prompts["anchors"]
        self.assertTrue(anchors["shared_across_variants"])
        self.assertEqual(anchors["status"], "illustrative_not_exhaustive")
        self.assertTrue(anchors["shared_across_label_orders"])
        for example in anchors["examples"]:
            for order, system in self.renderings.items():
                with self.subTest(anchor=example["text"], order=order):
                    self.assertIn(example["text"], system)
            for variant in self.prompts["variants"]:
                with self.subTest(anchor=example["text"], variant=variant["variant_id"]):
                    self.assertNotIn(example["text"], variant["question"])

    def test_the_withdrawn_rules_reach_no_model(self):
        """The four withdrawn rules must not survive in what is sent."""

        for order, system in self.renderings.items():
            for fragment in (
                "public health, prevention or widened access",
                "populations that are normally excluded",
                "cultural preservation, inclusion or public access",
                "Generic job creation",
            ):
                with self.subTest(order=order, fragment=fragment):
                    self.assertNotIn(fragment, system)

    def test_the_kept_rules_survive_in_both_renderings(self):
        for order, system in self.renderings.items():
            for fragment in (
                "integral to the offering, whether current or planned",
                "may qualify even when it reaches direct users",
                "green, ethical, sustainable or community",
                "founder's intentions or an incidental donation",
                "Fair trade or improved working conditions qualify only when",
                "the information is insufficient",
                "probability of success",
                "realised ex post causal impact",
            ):
                with self.subTest(order=order, fragment=fragment):
                    self.assertIn(fragment, system)

    def test_a_missing_protection_sentence_is_rejected(self):
        broken = deep_copy(self.prompts)
        broken["system_prompt"]["template"] = broken["system_prompt"]["template"].replace(
            PROTECTION_SENTENCE, ""
        )
        with self.assertRaisesRegex(SchemaError, "content to classify"):
            validate_camuffo_prompts(broken)

    def test_a_missing_delimiter_is_rejected(self):
        broken = deep_copy(self.prompts)
        broken["assembly"]["delimiter"]["open"] = ""
        with self.assertRaisesRegex(SchemaError, "delimiter.open"):
            validate_camuffo_prompts(broken)

    def test_an_anchor_moved_into_a_question_is_rejected(self):
        broken = deep_copy(self.prompts)
        broken["variants"][0]["question"] += " Premium leather accessories is 0."
        with self.assertRaisesRegex(SchemaError, "must not appear in question"):
            validate_camuffo_prompts(broken)

    def test_realised_impact_instruction_is_the_corrected_one(self):
        for order, system in self.renderings.items():
            with self.subTest(order=order):
                self.assertIn(
                    "do not require evidence of realised ex post causal impact", system
                )
                self.assertIn(
                    "Evaluate the concrete and plausible benefit mechanism "
                    "described in the campaign.",
                    system,
                )
                self.assertNotIn("causal impact actually realised", system)

    def test_the_three_questions_are_recorded_as_authored_ex_ante(self):
        for variant in self.prompts["variants"]:
            with self.subTest(variant=variant["variant_id"]):
                self.assertEqual(variant["source"], "researcher_authored_ex_ante")

    def test_no_forbidden_strategy_elements(self):
        for variant in self.prompts["variants"]:
            lowered = variant["question"].lower()
            for token in ("as a ", "as an ", "step by step", "examples:", "explain", "reasoning"):
                with self.subTest(variant=variant["variant_id"], token=token):
                    self.assertNotIn(token, lowered)

    def test_samples_rationale_records_the_adaptation(self):
        rationale = self.prompts["samples_rationale"]
        self.assertIn("below", rationale.lower())
        self.assertIn("Camuffo", rationale)

    def test_role_prompting_is_rejected(self):
        broken = deep_copy(self.prompts)
        broken["variants"][1]["question"] = "As an expert, does the main product or service described in the campaign text below provide a substantive benefit to society?"
        with self.assertRaises(SchemaError):
            validate_camuffo_prompts(broken)

    def test_identical_questions_are_rejected(self):
        broken = deep_copy(self.prompts)
        broken["variants"][1]["question"] = broken["variants"][0]["question"]
        with self.assertRaisesRegex(SchemaError, "differ"):
            validate_camuffo_prompts(broken)

    def test_two_variants_are_rejected(self):
        broken = deep_copy(self.prompts)
        broken["variants"] = broken["variants"][:2]
        with self.assertRaises(SchemaError):
            validate_camuffo_prompts(broken)


class CrossFileConsistencyTests(unittest.TestCase):
    """The three files must speak about the construct in one single way."""

    def setUp(self):
        self.rubric = load_json(RUBRIC_PATH)
        self.labels = load_json(LABELS_PATH)
        self.camuffo = load_json(CAMUFFO_PATH)
        self.camuffo_system = render_system_prompt(self.camuffo, "10")

    def test_the_real_files_are_consistent(self):
        verify_qualifier_consistency(self.rubric, self.labels, self.camuffo)
        verify_anchor_consistency(self.rubric, self.camuffo)

    def test_the_canonical_qualifier_is_used_in_all_three(self):
        self.assertIn(CANONICAL_QUALIFIER, self.rubric["assign_1_when"]["requirement"])
        for label in self.labels["labels"]:
            with self.subTest(label=label["value"]):
                self.assertIn(CANONICAL_QUALIFIER, label["meaning"])
        self.assertIn(CANONICAL_QUALIFIER, self.camuffo_system)

    def test_a_superseded_wording_survives_only_as_a_recorded_supersession(self):
        """It may be named in the audit trail, never used as the construct."""

        for wording in SUPERSEDED_QUALIFIERS:
            with self.subTest(wording=wording):
                self.assertIn(wording, self.rubric["qualifier"]["superseded_expressions"])
                for where, text in (
                    ("rubric requirement", self.rubric["assign_1_when"]["requirement"]),
                    ("system instruction", self.camuffo_system),
                ):
                    with self.subTest(where=where):
                        self.assertNotIn(wording, text)
                for label in self.labels["labels"]:
                    with self.subTest(label=label["value"]):
                        self.assertNotIn(wording, label["meaning"])

    def test_no_forbidden_wording_is_used_anywhere(self):
        for wording in FORBIDDEN_QUALIFIERS:
            with self.subTest(wording=wording):
                self.assertNotIn(wording, self.rubric["assign_1_when"]["requirement"])
                self.assertNotIn(wording, self.camuffo_system)
                for variant in self.camuffo["variants"]:
                    self.assertNotIn(wording, variant["question"])

    def test_a_reintroduced_superseded_wording_is_caught(self):
        drifted = deep_copy(self.labels)
        drifted["labels"][0]["meaning"] = (
            "No benefit beyond the ordinary private utility of the consumer."
        )
        with self.assertRaises(QualifierInconsistency) as context:
            verify_qualifier_consistency(self.rubric, drifted, self.camuffo)
        self.assertIn("superseded", str(context.exception))

    def test_a_forbidden_wording_in_a_question_is_caught(self):
        drifted = deep_copy(self.camuffo)
        drifted["variants"][0]["question"] = "Does it benefit society beyond its direct consumers?"
        with self.assertRaises(QualifierInconsistency) as context:
            verify_qualifier_consistency(self.rubric, self.labels, drifted)
        self.assertIn("forbidden", str(context.exception))

    def test_anchors_drifting_between_the_two_files_is_caught(self):
        drifted = deep_copy(self.camuffo)
        drifted["anchors"]["examples"][2]["label"] = 1
        with self.assertRaises(AnchorInconsistency):
            verify_anchor_consistency(self.rubric, drifted)

    def test_an_anchor_dropped_from_the_template_is_caught(self):
        drifted = deep_copy(self.camuffo)
        drifted["system_prompt"]["template"] = drifted["system_prompt"]["template"].replace(
            '"Premium leather accessories" = 0 because the benefit is consumer-only.', ""
        )
        with self.assertRaisesRegex(AnchorInconsistency, "missing from the shared"):
            verify_anchor_consistency(self.rubric, drifted)


class ExperimentAndGateTests(unittest.TestCase):
    def setUp(self):
        self.experiment = load_json(EXPERIMENT_PATH)

    def test_reference_hashes_match_the_files_on_disk(self):
        # D-EXPORT-01: the third-party source paper is not redistributed with the
        # review package, so there this check is skipped, never counted as passed.
        if not (PROJECT_ROOT / self.experiment["references"]["source_paper"]["file"]).is_file():
            self.skipTest("the third-party source paper is not in this copy (D-EXPORT-01)")
        verify_reference_hashes(self.experiment, PROJECT_ROOT)

    def test_reference_hashes_of_the_protocol_files_match(self):
        """Rubric, labels and both prompt files, checked even without the source paper."""

        protocol = deep_copy(self.experiment)
        del protocol["references"]["source_paper"]
        self.assertEqual(
            set(verify_reference_hashes(protocol, PROJECT_ROOT)),
            {"rubric", "labels", "camuffo_prompts", "carlson_prompts"},
        )

    def test_a_drifted_reference_is_detected(self):
        broken = deep_copy(self.experiment)
        broken["references"]["rubric"]["canonical_json_sha256"] = "0" * 64
        with self.assertRaises(HashMismatch):
            verify_reference_hashes(broken, PROJECT_ROOT)

    def test_the_experiment_and_its_references_agree_on_every_status(self):
        verify_approval_consistency(self.experiment, PROJECT_ROOT)

    def test_a_status_forged_in_the_experiment_alone_is_detected(self):
        """The experiment cannot disagree with the file it points at."""

        forged = deep_copy(self.experiment)
        forged["references"]["camuffo_prompts"]["approval_status"] = "pending_approval"
        with self.assertRaises(ApprovalInconsistency) as context:
            verify_approval_consistency(forged, PROJECT_ROOT)
        self.assertIn("camuffo_prompts", str(context.exception))

    def test_all_four_gates_are_open(self):
        for name in ("rubric", "labels", "camuffo_prompts", "carlson_prompts"):
            with self.subTest(gate=name):
                self.assertEqual(
                    self.experiment["references"][name]["approval_status"], "approved"
                )
        self.assertEqual(approval_gates(self.experiment), [])
        require_approved(self.experiment)

    def test_a_single_closed_gate_still_blocks(self):
        for name in ("rubric", "labels", "camuffo_prompts", "carlson_prompts"):
            partial = deep_copy(self.experiment)
            partial["references"][name]["approval_status"] = "pending_approval"
            with self.subTest(closed_gate=name):
                with self.assertRaises(ApprovalBlocked) as context:
                    require_approved(partial)
                self.assertIn(name, str(context.exception))

    def test_the_definitive_gate_list_names_all_four_references(self):
        gates = self.experiment["generation_gates"]["definitive_manifest_requires"]
        self.assertEqual(len(gates), 4)
        for name in ("rubric", "labels", "camuffo_prompts", "carlson_prompts"):
            with self.subTest(gate=name):
                self.assertTrue(any(f"references.{name}." in gate for gate in gates))

    def test_expected_call_counts(self):
        counts = self.experiment["expected_calls"]
        self.assertEqual(counts["pilot_deepseek"], {"camuffo": 108, "carlson": 84, "total": 192})
        self.assertEqual(counts["pilot_full"], {"camuffo": 324, "carlson": 252, "total": 576})
        self.assertEqual(counts["full"], {"camuffo": 6750, "carlson": 5250, "total": 12000})
        self.assertEqual(
            counts["smoke_one_call_per_template"],
            {"camuffo": 3, "carlson": 7, "total": 10},
        )

    def test_counts_follow_from_the_design(self):
        arms = self.experiment["arms"]
        items, models = 250, 3
        camuffo = arms["camuffo"]["P"] * arms["camuffo"]["S"] * items * models
        carlson = arms["carlson"]["strategies"] * arms["carlson"]["S"] * items * models
        self.assertEqual(camuffo, 6750)
        self.assertEqual(carlson, 5250)
        self.assertEqual(camuffo + carlson, 12000)

    def test_no_credentials_anywhere_in_the_config_tree(self):
        """No credential-bearing key, and no value that looks like a key.

        Prose may legitimately mention the word 'secret'; a JSON *key* named
        for a credential, or a value shaped like one, may not.
        """

        forbidden_keys = {"api_key", "apikey", "secret", "token", "password", "bearer"}
        key_like = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{8,})")

        def walk(node, path, file_name):
            if isinstance(node, dict):
                for key, value in node.items():
                    with self.subTest(file=file_name, key=f"{path}.{key}"):
                        self.assertNotIn(key.lower(), forbidden_keys)
                    walk(value, f"{path}.{key}", file_name)
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]", file_name)
            elif isinstance(node, str):
                with self.subTest(file=file_name, path=path):
                    self.assertIsNone(key_like.search(node))

        for config_path in CONFIG.rglob("*.json"):
            walk(load_json(config_path), config_path.stem, config_path.name)

    def test_the_camuffo_arm_is_not_claimed_as_a_literal_replication(self):
        label = self.experiment["design_label"]
        self.assertEqual(
            label["camuffo_arm"], "feasibility-adapted Camuffo-type variance-aware design"
        )
        self.assertIn("never be described as a literal replication", label["rule"])

    def test_every_deviation_from_camuffo_is_recorded(self):
        ids = {entry["id"] for entry in self.experiment["deviations_from_camuffo"]}
        self.assertEqual(
            ids,
            {
                "samples_below_recommended",
                "no_independent_audit_set",
                "reconstructed_rubric",
                "temperature_provider_dependent",
                "one_token_cap_untested",
                "counterbalancing_camuffo_only",
                "pilot_shape",
            },
        )
        for entry in self.experiment["deviations_from_camuffo"]:
            with self.subTest(deviation=entry["id"]):
                self.assertTrue(entry["deviation"])

    def test_the_pilot_shape_deviation_names_both_designs(self):
        entry = next(
            d for d in self.experiment["deviations_from_camuffo"] if d["id"] == "pilot_shape"
        )
        self.assertIn("12 items", entry["deviation"])
        self.assertIn("20x1x1", entry["deviation"])

    def test_sharing_is_disabled(self):
        self.assertFalse(self.experiment["sharing"]["enabled"])

    def test_carlson_strategies_are_never_aggregated(self):
        self.assertFalse(self.experiment["arms"]["carlson"]["aggregate_across_strategies"])

    def test_live_calls_remain_disabled(self):
        execution = self.experiment["execution"]
        self.assertFalse(execution["live_calls_enabled"])
        self.assertTrue(execution["require_explicit_live_flag"])
        self.assertTrue(execution["require_budget_cap"])
        self.assertTrue(execution["retries_are_not_replicates"])
        self.assertEqual(execution["reasoning_policy"], "provider_native_disabled")


class CatalogBuildTests(unittest.TestCase):
    def setUp(self):
        self.experiment = load_json(EXPERIMENT_PATH)

    def test_a_definitive_catalog_now_builds(self):
        entries = build_catalog(self.experiment, PROJECT_ROOT)
        self.assertEqual(len(selectable_templates(entries)), 10)

    def test_a_definitive_catalog_is_blocked_again_if_a_gate_closes(self):
        closed = deep_copy(self.experiment)
        closed["references"]["camuffo_prompts"]["approval_status"] = "pending_approval"
        with self.assertRaises(ApprovalBlocked):
            build_catalog(closed, PROJECT_ROOT)

    def test_inspection_build_yields_ten_selectable_templates(self):
        entries = build_catalog(self.experiment, PROJECT_ROOT, include_unapproved=True)
        selectable = selectable_templates(entries)
        self.assertEqual(len(selectable), 10)
        self.assertEqual(sum(1 for e in selectable if e.arm == "carlson"), 7)
        self.assertEqual(sum(1 for e in selectable if e.arm == "camuffo"), 3)

    def test_corrupted_template_is_present_but_not_selectable(self):
        entries = build_catalog(self.experiment, PROJECT_ROOT, include_unapproved=True)
        corrupted = [e for e in entries if e.canonical_status == "corrupted"]
        self.assertEqual(len(corrupted), 1)
        self.assertFalse(corrupted[0].selectable)
        self.assertNotIn(corrupted[0], selectable_templates(entries))

    def test_every_entry_records_provenance_and_hash(self):
        for entry in selectable_templates(
            build_catalog(self.experiment, PROJECT_ROOT, include_unapproved=True)
        ):
            with self.subTest(template=entry.template_id):
                self.assertEqual(len(entry.prompt_sha256), 64)
                self.assertEqual(
                    entry.prompt_sha256, sha256_bytes(entry.text.encode("utf-8"))
                )
                self.assertTrue(entry.origin)
                self.assertTrue(entry.origin_ref)
                self.assertEqual(entry.response_contract, "binary_exact")

    def test_carlson_entries_cite_the_paper_table(self):
        entries = build_catalog(self.experiment, PROJECT_ROOT, include_unapproved=True)
        for entry in entries:
            if entry.arm == "carlson" and entry.selectable:
                with self.subTest(template=entry.template_id):
                    self.assertEqual(entry.origin, "table3_paper")
                    self.assertIn("carlson_burbano_2026.pdf", entry.origin_ref)
                    self.assertIn("Table 3", entry.origin_ref)

    def test_camuffo_entries_share_one_system_instruction_hash(self):
        entries = build_catalog(self.experiment, PROJECT_ROOT, include_unapproved=True)
        hashes = {e.system_template_sha256 for e in entries if e.arm == "camuffo"}
        self.assertEqual(len(hashes), 1)
        self.assertIsNotNone(hashes.pop())

    def test_catalog_is_deterministic(self):
        first = build_catalog(self.experiment, PROJECT_ROOT, include_unapproved=True)
        second = build_catalog(self.experiment, PROJECT_ROOT, include_unapproved=True)
        self.assertEqual([e.as_record() for e in first], [e.as_record() for e in second])


class FrozenArtifactTests(unittest.TestCase):
    def test_existing_artifact_is_never_clobbered(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "catalog.jsonl"
            write_jsonl([{"a": 1}], target)
            with self.assertRaises(FrozenArtifact):
                write_jsonl([{"a": 2}], target)
            self.assertEqual(target.read_text(encoding="utf-8").strip(), '{"a": 1}')

    def test_jsonl_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "catalog.jsonl"
            records = [{"template_id": "x", "n": 1}, {"template_id": "y", "n": 2}]
            write_jsonl(records, target)
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line) for line in lines], records)


if __name__ == "__main__":
    unittest.main()
