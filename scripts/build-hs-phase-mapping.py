#!/usr/bin/env python3
"""Map HubSpot theme modules/sections to Build plan phase tasks."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
CATALOG = ROOT / "hs-catalog.json"
OUT_JSON = ROOT / "hs-phase-mapping.json"
OUT_JS = ROOT / "hs-phase-mapping.data.js"

# slug -> (phaseId, confidence, reason)
MODULE_MAP: dict[str, tuple[str, str, str]] = {
    "features-stacked-content": (
        "task-twocol",
        "high",
        "Stacked Content Block — primary Two-column HubSpot module (features-stacked-content CSS / section.grid layout).",
    ),
    "FAQs": ("task-faq", "high", "FAQs section module — accordion FAQ pattern (div.o-faq)."),
    "faq2": ("task-faq", "medium", "FAQ 2 variant — same accordion pattern as FAQ section."),
    "features-unfold": ("task-featuresunfold", "high", "Features Unfold module (section.fu interactive reveal)."),
    "icon-cards": ("task-iconcards", "high", "Icon Cards grid (div.icon-cards-wrapper)."),
    "icons-list": ("task-icon-list-grid", "high", "Icons List — icon tile + label grid (Module: Icons List)."),
    "card-segmentation": (
        "task-cards",
        "high",
        "Card Segmentation — Cards section (dl#cards-events grid).",
    ),
    "features-card": ("task-cards", "medium", "Features Card — alternate cards row variant."),
    "card": ("task-cards", "low", "Generic card module — likely sub-element of Cards section."),
    "stats-set": ("task-stats-section", "high", "Stats Set bar — page-level metrics (section.global.global-4-stats)."),
    "stats-set-stacked": (
        "task-global-stats",
        "high",
        "Stats Set Stacked — Global stats block (stats-set-stacked-wrapper).",
    ),
    "stat": ("task-stats", "high", "Stats primitive — value + label pair used inside Two-column."),
    "features-horizontal-slider": (
        "task-horizontal-slider",
        "high",
        "Features Horizontal Slider — scrollable card row.",
    ),
    "testimonial-slider": (
        "task-customer-story",
        "high",
        "Testimonial slider — customer story carousel content.",
    ),
    "testimonial-slider-alt": (
        "task-customer-story",
        "medium",
        "Alternate testimonial slider — same customer-story use case.",
    ),
    "testimonial-carousel": (
        "task-testimonial-carousel",
        "high",
        "Testimonial Carousel module — Phase 4 global carousel.",
    ),
    "features-pricing-card": ("task-pricing-widget", "high", "Features Pricing Card — plan comparison cards."),
    "card-pricing": ("task-pricing-widget", "high", "Card Pricing — pricing tier cards on /pricing."),
    "pricing-card": ("task-pricing-widget", "medium", "Pricing Cards module — plan row variant."),
    "features-pricing": ("task-pricing-widget", "medium", "Features Pricing Card alias."),
    "rp-pricing-card": ("task-pricing-widget", "medium", "RP Pricing Card — pricing page variant."),
    "gx-pricing-card": ("task-pricing-widget", "medium", "GX Pricing Card — gated content pricing."),
    "Pricing Widget": ("task-pricing-widget", "high", "Pricing Widget module label match."),
    "sections": ("task-pricing-widget", "low", "Pricing section bundle — pricing page composite."),
    "tabs": ("task-addons", "medium", "Tabs module on pricing page — used for Add-ons band."),
    "cta": ("task-cta", "high", "CTA Banner (section.cta-module conversion band)."),
    "announcement": ("task-announcement-bar", "high", "Announcement module — optional page banner strip."),
    "heading-composition": (
        "task-text",
        "high",
        "Header Composition — Text block (eyebrow + heading + body).",
    ),
    "feature-block-list": ("task-features-list", "high", "Feature Block List — scannable bullet feature list."),
    "features-detail": (
        "task-features-index",
        "high",
        "Features Detail — feature index / detail grid on /features.",
    ),
    "information-card": ("task-reports", "high", "Information Card — report/resource card grid."),
    "reports": ("task-reports", "high", "Reports module — gated resource cards."),
    "link-cards": ("task-categorylinks", "high", "Link Cards — grouped category link lists."),
    "custom-form": ("task-form-section", "high", "Custom Form — lead-capture form section."),
    "Form and Hubspot meeting": ("task-form-section", "medium", "Form + meeting embed — conversion form variant."),
    "partnerships-form": ("task-form-section", "medium", "Partnerships form — form section variant."),
    "media-frame": ("task-video-hero-section", "high", "Media Frame — hero video/image frame module."),
    "video-hero": ("task-video-hero-section", "high", "Video Hero — full-bleed video hero."),
    "image-video-modal": ("task-video", "medium", "Image/video modal — Video primitive variant."),
    "results-list": ("task-use-case-section", "high", "Results List — case-study results sidebar metrics."),
    "case-study": ("task-introduction-summary", "high", "Case Study module (article.case-study intro block)."),
    "interactive-summary": (
        "task-introduction-summary",
        "medium",
        "Interactive Summary — customer-story intro with accordion.",
    ),
    "service-detail": ("task-service-detail", "high", "Service Detail — professional services breakdown."),
    "service-list": ("task-services-section", "medium", "Service List — services overview columns."),
    "hero-full-introduction": (
        "task-special-hero-introduction",
        "high",
        "Hero Full Introduction (section.hero-full-introduction).",
    ),
    "special-heading": ("task-special-hero-introduction", "medium", "Special Heading — display hero heading."),
    "special-intro": ("task-special-hero-introduction", "medium", "Special Intro — hero introduction copy."),
    "feature-introduction": ("task-special-hero-introduction", "medium", "Feature Introduction — hero intro variant."),
    "quote": ("task-quote", "high", "Quote primitive — single testimonial block."),
    "quote-new": ("task-dual-quote", "medium", "New Quote — may render paired quotes; maps to Dual quote."),
    "button": ("task-button", "high", "Main Button module."),
    "button-stack": ("task-button", "high", "Button stack — multiple Button instances."),
    "logo-set-global": ("task-logo-carousel", "high", "Logo Set Global — logo strip / carousel."),
    "logo-set-global-new": ("task-logo-carousel", "medium", "Logo Set Global (new variant)."),
    "logo-set-global-logos-only": ("task-logo-carousel", "medium", "Logo Set — logos-only variant."),
    "logo-set": ("task-logo-carousel", "low", "logo-set — partial logo strip."),
    "header-theme": ("task-header", "high", "Global Header theme shell."),
    "mega-menu": ("task-header", "high", "Mega menu — part of Header navigation."),
    "menu": ("task-header", "medium", "Menu module — navigation element in Header."),
    "widget-user-review": ("task-user-review-widget", "high", "User review widget — Phase 4 global."),
    "widget-industry-rating": ("task-trust-banner", "medium", "Industry rating widget — trust/rating strip."),
    "widget-gx-show": ("task-trust-banner", "low", "GX Show widget — trust/content widget."),
    "badge-set": ("task-trust-banner", "medium", "Badges Set — trust badge row."),
    "text-banner": ("task-cta", "low", "Text Banner — compact CTA/text band."),
    "advanced-image": ("task-image", "high", "Advanced Image — Image primitive variant."),
    "animated-hero": ("task-special-hero-introduction", "medium", "Animated Hero — hero introduction with motion."),
    "interactive-hero": ("task-special-hero-introduction", "medium", "Interactive Hero — hero intro section."),
    "industry-selector": ("task-industries-widget", "high", "Industry Selector — Industries widget."),
    "industry-selector-global": (
        "task-industries-widget",
        "high",
        "Industry Selector (Global) — Industries widget.",
    ),
    "industry-selector-features-global": (
        "task-industry-vertical",
        "high",
        "Industry Selector Features — industry vertical page section.",
    ),
    "features-selector-global": ("task-features-widget", "medium", "Features selector — Phase 4 features widget."),
    "widget-group": ("task-features-widget", "low", "Widget group — composite features widget shell."),
    "widget-stats": ("task-company-stats", "low", "Stats widget — partial match for Company stats widget."),
    "social-icons-set": ("task-footer", "medium", "Social icons — footer social links set."),
    "comparison-table": ("task-cards", "low", "Comparison table — card/table hybrid; partial Cards match."),
    "confetti-section": ("task-reports", "low", "Confetti — campaign/rollup flourish near gated content."),
    "confetti": ("task-reports", "low", "Confetti module — rollup/report pages."),
    "blog-cards": ("task-reports", "low", "Blog cards — content card grid; partial Reports match."),
    "card-blog-posts": ("task-reports", "low", "Blog post cards — resource listing."),
    "monthly-features": ("task-features-widget", "low", "Monthly features — features widget content."),
    "features-by-month": ("task-features-widget", "low", "Features by month — widget content."),
}

SECTION_MAP: dict[str, tuple[str, str, str]] = {
    "s-features-stacked-content": (
        "task-twocol",
        "high",
        "Features Stacked content section — pre-composed Two-column.",
    ),
    "s-featured-image": ("task-twocol", "high", "Featured Image section — two-column image + copy layout."),
    "s-info-image-left": (
        "task-twocol",
        "high",
        "Info with landscape image on the left — two-column layout.",
    ),
    "s-info-image-right": (
        "task-twocol",
        "medium",
        "Info with landscape image on the right — mirrored Two-column.",
    ),
    "s-multi-row-content": ("task-twocol", "medium", "Multi-row content — stacked two-column rows."),
    "s-two-column": ("task-twocol", "high", "Two Column Section — explicit two-column section template."),
    "s-hero": ("task-special-hero-introduction", "high", "Hero section — display hero introduction."),
    "s-page-header": ("task-special-hero-introduction", "medium", "Page header hero variant."),
    "s-hero-partner": ("task-special-hero-introduction", "medium", "Hero Partner — partner page hero."),
    "s-hero-product-explainer": (
        "task-special-hero-introduction",
        "medium",
        "Hero Product Explainer — product hero intro.",
    ),
    "s-hero-product-tour": (
        "task-special-hero-introduction",
        "medium",
        "Hero Product Tour — product tour hero.",
    ),
    "s-case-study": ("task-introduction-summary", "high", "Case Study section — customer story intro."),
    "s-event-premium-header": (
        "task-introduction-summary",
        "medium",
        "Event premium header — case-study-style intro.",
    ),
    "s-customer-stories": ("task-customer-story", "high", "Customer Stories section template."),
    "s-testimonial-carousel": ("task-customer-story", "high", "Testimonial Carousel section."),
    "s-features-horizontal-slider": (
        "task-horizontal-slider",
        "high",
        "Features Horizontal Slider section.",
    ),
    "s-services": ("task-service-detail", "high", "Services detail content section."),
    "s-logo-set": ("task-logo-carousel", "high", "Logo Set section — logo carousel strip."),
    "s-subscription-plans": (
        "task-implementation-packages",
        "medium",
        "Subscription Plans — onboarding/pricing package cards.",
    ),
    "s-quote-two-columns": ("task-dual-quote", "high", "Quote two columns — side-by-side dual quote layout."),
    "s-get-started": ("task-cta", "medium", "Get started section — CTA conversion band."),
    "s-industry-selector": ("task-industry-vertical", "high", "Industry Selector section."),
    "s-widgets": ("task-features-widget", "medium", "Widgets section — composite global widgets row."),
    "s-4-bullet-content": ("task-use-case-section", "low", "4 Bullets + results — partial use-case layout."),
    "s-comparison": ("task-cards", "low", "Comparison section — card/table layout."),
    "s-integration-bar": ("task-twocol", "low", "Integration bar — two-column CTA + image."),
    "s-useful-links": ("task-categorylinks", "medium", "Useful Links — category link lists."),
    "s-rollup": ("task-reports", "medium", "Rollup section — gated report landing pattern."),
    "s-key-takeaways": ("task-reports", "low", "Key Takeaways — pulse/report content block."),
}

# Phase tasks extracted from index — tasks without any HS mapping
PHASE_TASKS = [
    ("task-button", 2, "Button"),
    ("task-text", 2, "Text"),
    ("task-image", 2, "Image"),
    ("task-video", 2, "Video"),
    ("task-quote", 2, "Quote"),
    ("task-stats", 2, "Stats"),
    ("task-twocol", 3, "Two-column"),
    ("task-twocol-bigger", 3, "Two-column with bigger left"),
    ("task-twocol-text-heavy", 3, "Two-column — text-heavy"),
    ("task-flat-one-column", 3, "Flat one column"),
    ("task-centeredtext", 3, "Centered text block"),
    ("task-dual-quote", 3, "Dual quote"),
    ("task-special-hero-introduction", 3, "Special hero introduction"),
    ("task-iconcards", 3, "Icon cards"),
    ("task-cards", 3, "Cards"),
    ("task-icon-list-grid", 3, "Icon list grid"),
    ("task-image-icon-grid-list", 3, "Image with icon grid list"),
    ("task-services-section", 3, "Services section"),
    ("task-service-detail", 3, "Service detail"),
    ("task-video-hero-section", 3, "Video hero section"),
    ("task-introduction-summary", 3, "Introduction summary"),
    ("task-use-case-section", 3, "Use case section"),
    ("task-form-section", 3, "Form section"),
    ("task-pricing-widget", 3, "Pricing widget"),
    ("task-addons", 3, "Addons"),
    ("task-faq", 3, "FAQ"),
    ("task-cta", 3, "CTA section"),
    ("task-featuresunfold", 3, "Features unfold"),
    ("task-reports", 3, "Reports"),
    ("task-categorylinks", 3, "Category links"),
    ("task-features-index", 3, "Features index"),
    ("task-stats-section", 3, "Stats section"),
    ("task-horizontal-slider", 3, "Horizontal slider"),
    ("task-customer-story", 3, "Customer story carousel"),
    ("task-industry-vertical", 3, "Industry vertical section"),
    ("task-features-list", 3, "Features list"),
    ("task-implementation-packages", 3, "Implementation packages"),
    ("task-announcement-bar", 3, "Announcement bar"),
    ("task-header", 4, "Header"),
    ("task-footer", 4, "Footer"),
    ("task-trust-banner", 4, "Trust banner"),
    ("task-logo-carousel", 4, "Logo carousel"),
    ("task-boxed-user-reviews", 4, "Boxed user reviews"),
    ("task-user-review-widget", 4, "User review widget"),
    ("task-features-widget", 4, "Features widget"),
    ("task-industries-widget", 4, "Industries widget"),
    ("task-company-stats", 4, "Company stats"),
    ("task-global-stats", 4, "Global stats"),
    ("task-testimonial-carousel", 4, "Testimonial carousel"),
]

PHASE_GAP_NOTES: dict[str, str] = {
    "task-twocol-bigger": "Layout variant of Two-column — no separate HubSpot module; uses features-stacked-content / section templates with different grid ratio.",
    "task-twocol-text-heavy": "Layout variant of Two-column — same HubSpot module, text-dominant column ratio.",
    "task-flat-one-column": "Composite section — assembled from heading-composition + button + image modules, not one HubSpot folder.",
    "task-centeredtext": "Centred text section — heading-composition with centre alignment; no dedicated module.",
    "task-image-icon-grid-list": "Composite — icons-list + side image; no single HubSpot module.",
    "task-services-section": "Services overview — closest HS match is service-list / multi-module section, not exact.",
    "task-footer": "Footer shell — assembled from HubSpot menu/text/form widgets + social-icons-set, no footer.module.",
    "task-boxed-user-reviews": "No dedicated HubSpot module found — may use widget-user-review in a section.",
    "task-company-stats": "No exact module — widget-stats is the closest partial match.",
}


def extract_phase_tasks_from_index() -> list[dict]:
    html = INDEX.read_text()
    tasks = []
    for m in re.finditer(
        r'<details class="task" id="(task-[^"]+)">.*?<span class="tname">([^<]+)',
        html,
        re.S,
    ):
        tid, name = m.group(1), re.sub(r"\s+", " ", m.group(1).split("<")[0] if "<" in m.group(2) else m.group(2))
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        name = re.split(r"<", name)[0].strip()
        phase = 3
        if "phase-2" in html[: html.find(f'id="{tid}"')]:
            phase = 2
        elif "phase-4" in html[: html.find(f'id="{tid}"')]:
            phase = 4
        # determine phase by position in file
        idx = html.find(f'id="{tid}"')
        p2 = html.find('id="phase-2"')
        p3 = html.find('id="phase-3"')
        p4 = html.find('id="phase-4"')
        if idx > p4:
            phase = 4
        elif idx > p3:
            phase = 3
        elif idx > p2:
            phase = 2
        else:
            phase = 1
        tasks.append({"id": tid, "phase": phase, "name": name.split("<")[0].strip()})
    return tasks


def build_mapping():
    catalog = json.loads(CATALOG.read_text())
    modules_out = {}
    sections_out = {}

    mapped_phase_ids: set[str] = set()

    for slug, mod in catalog["modules"].items():
        if slug in MODULE_MAP:
            phase_id, confidence, reason = MODULE_MAP[slug]
            phase_name = next((n for i, p, n in PHASE_TASKS if i == phase_id), phase_id)
            modules_out[slug] = {
                "hsSlug": slug,
                "hsLabel": mod["label"],
                "hsFolder": mod["folder"],
                "hsModuleId": mod.get("moduleId"),
                "phaseId": phase_id,
                "phaseName": phase_name,
                "phase": next(p for i, p, n in PHASE_TASKS if i == phase_id),
                "confidence": confidence,
                "reason": reason,
                "status": "mapped",
            }
            mapped_phase_ids.add(phase_id)
        else:
            modules_out[slug] = {
                "hsSlug": slug,
                "hsLabel": mod["label"],
                "hsFolder": mod["folder"],
                "hsModuleId": mod.get("moduleId"),
                "phaseId": None,
                "phaseName": None,
                "phase": None,
                "confidence": None,
                "reason": "No matching Build plan component identified — HubSpot-only or pulse/campaign-specific module.",
                "status": "not-in-build-plan",
            }

    for slug, sec in catalog["sections"].items():
        if slug in SECTION_MAP:
            phase_id, confidence, reason = SECTION_MAP[slug]
            phase_name = next((n for i, p, n in PHASE_TASKS if i == phase_id), phase_id)
            sections_out[slug] = {
                "hsSlug": slug,
                "hsLabel": sec["label"],
                "hsFile": sec["file"],
                "containsModules": sec.get("containsModules", []),
                "phaseId": phase_id,
                "phaseName": phase_name,
                "phase": next(p for i, p, n in PHASE_TASKS if i == phase_id),
                "confidence": confidence,
                "reason": reason,
                "status": "mapped",
            }
            mapped_phase_ids.add(phase_id)
        else:
            sections_out[slug] = {
                "hsSlug": slug,
                "hsLabel": sec["label"],
                "hsFile": sec["file"],
                "containsModules": sec.get("containsModules", []),
                "phaseId": None,
                "phaseName": None,
                "phase": None,
                "confidence": None,
                "reason": "Pulse/report/campaign section — not in current Build plan phases.",
                "status": "not-in-build-plan",
            }

    phase_gaps = []
    for tid, phase, name in PHASE_TASKS:
        if tid not in mapped_phase_ids:
            phase_gaps.append(
                {
                    "phaseId": tid,
                    "phase": phase,
                    "phaseName": name,
                    "note": PHASE_GAP_NOTES.get(
                        tid,
                        "No dedicated HubSpot module — likely a layout variant or composite of other modules.",
                    ),
                    "relatedHs": [
                        s
                        for s, m in modules_out.items()
                        if m.get("phaseId") and tid.replace("task-", "") in s.replace("-", "")
                    ][:3],
                }
            )

    mapped_mod = sum(1 for m in modules_out.values() if m["status"] == "mapped")
    mapped_sec = sum(1 for s in sections_out.values() if s["status"] == "mapped")

    data = {
        "version": 1,
        "generated": "2026-06",
        "stats": {
            "hsModules": len(modules_out),
            "hsSections": len(sections_out),
            "mappedModules": mapped_mod,
            "unmappedModules": len(modules_out) - mapped_mod,
            "mappedSections": mapped_sec,
            "unmappedSections": len(sections_out) - mapped_sec,
            "phaseTasks": len(PHASE_TASKS),
            "phaseWithHsMatch": len(mapped_phase_ids),
            "phaseWithoutHsMatch": len(PHASE_TASKS) - len(mapped_phase_ids),
        },
        "modules": modules_out,
        "sections": sections_out,
        "phaseGaps": phase_gaps,
        "byPhase": {},
    }

    for tid, phase, name in PHASE_TASKS:
        hs_mods = [m for m in modules_out.values() if m.get("phaseId") == tid]
        hs_secs = [s for s in sections_out.values() if s.get("phaseId") == tid]
        if hs_mods or hs_secs or tid in [g["phaseId"] for g in phase_gaps]:
            data["byPhase"][tid] = {
                "phaseId": tid,
                "phase": phase,
                "phaseName": name,
                "hsModules": hs_mods,
                "hsSections": hs_secs,
                "gap": next((g for g in phase_gaps if g["phaseId"] == tid), None),
            }

    return data


def main():
    data = build_mapping()
    OUT_JSON.write_text(json.dumps(data, indent=2) + "\n")
    OUT_JS.write_text("window.HS_PHASE_MAPPING=" + json.dumps(data, separators=(",", ":")) + ";\n")
    s = data["stats"]
    print(f"Wrote {OUT_JSON.name}")
    print(f"  Modules mapped: {s['mappedModules']}/{s['hsModules']}")
    print(f"  Sections mapped: {s['mappedSections']}/{s['hsSections']}")
    print(f"  Phase tasks with HS match: {s['phaseWithHsMatch']}/{s['phaseTasks']}")
    print(f"  Phase gaps (no HS module): {s['phaseWithoutHsMatch']}")


if __name__ == "__main__":
    main()
