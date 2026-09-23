"""AgentCore Platform v1.0 - INS-C2-013 domain services.

Pure, deterministic helpers — no agenticstar/framework imports here.
Scope-advisory detection, TCFD/IAIS query classification, and mock KB
retrieval + answer composition for the insurance climate-risk / TCFD
disclosure Q&A domain.
"""

import re
from typing import Any

SCOPE_ADVISORY_DISCLAIMER = (
    "ポートフォリオ固有のリスク定量化には専門的な気候リスク分析が必要です。"
    "本エージェントは TCFD/IAIS 手法ガイダンスのみ提供します。"
    "定量評価には資格を持つ気候リスク専門家にご相談ください。"
)

# Portfolio-specific climate risk quantification is out of scope for a
# methodology/compliance Q&A agent — this is a business-logic scope gate,
# not a trust-level escalation.
_PORTFOLIO_QUANT_RE = re.compile(
    r"(自社\s*ポートフォリオ|自社の保有資産|保有資産.*(定量|算出)|"
    r"リスク量\s*(を)?\s*(算出|計算|定量化)|"
    r"portfolio[- ]specific|quantify (our|my) portfolio|"
    r"our (holdings|portfolio).*(quantif|calculate|var)|climate var\b)",
    re.IGNORECASE,
)

CATEGORY_KEYWORDS = {
    "physical_risk": (
        "物理的リスク",
        "自然災害",
        "洪水",
        "台風",
        "海面上昇",
        "physical risk",
        "flood",
        "extreme weather",
    ),
    "transition_risk": ("移行リスク", "炭素税", "脱炭素", "政策変更", "transition risk", "carbon tax", "policy shift"),
    "scenario_analysis": ("シナリオ分析", "1.5度", "2度シナリオ", "scenario analysis", "ipcc", "ngfs scenario"),
    "disclosure_format": ("開示様式", "開示フォーマット", "有価証券報告書", "disclosure format", "tse disclosure"),
    "insurance_sector_specific": (
        "保険引受",
        "保険料率",
        "再保険",
        "insurance underwriting",
        "reinsurance",
        "insurance premium",
    ),
    "iais_supervision": ("iais", "保険監督", "監督上の期待", "supervisory expectations", "insurance supervision"),
}

INSURANCE_OVERLAY_CATEGORIES = ("insurance_sector_specific", "iais_supervision")

# Mock KB — tcfd_fsa_climate namespace (TCFD Final Recommendations 2017 +
# Supplemental Guidance for the Financial Sector 2020 + IPCC AR6 + Japan
# FSA/NGFS/TSE climate-disclosure guidance).
TCFD_FSA_CLIMATE_KB = [
    {
        "category": "physical_risk",
        "provision_id": "TCFD-2017-PhysicalRisk-1",
        "summary": "急性・慢性の物理的リスクを気候関連財務情報として開示することを推奨",
        "source": "TCFD Final Recommendations (2017)",
    },
    {
        "category": "transition_risk",
        "provision_id": "TCFD-2020-Supp-TransitionRisk-1",
        "summary": "政策・法規制・技術・市場の移行リスクを金融セクター向け補足ガイダンスに基づき評価",
        "source": "TCFD Supplemental Guidance for Financial Sector (2020)",
    },
    {
        "category": "scenario_analysis",
        "provision_id": "IPCC-AR6-Scenario-1",
        "summary": "1.5度・2度・4度シナリオを用いた気候関連シナリオ分析の実施を推奨",
        "source": "IPCC AR6 scenario summary",
    },
    {
        "category": "disclosure_format",
        "provision_id": "FSA-2025-DisclosureFormat-1",
        "summary": "有価証券報告書における気候関連開示の様式・記載項目に関するFSAガイダンス",
        "source": "Japan FSA Climate Disclosure Guidance (2025)",
    },
    {
        "category": "disclosure_format",
        "provision_id": "TSE-ClimateDisclosure-1",
        "summary": "東証上場企業向け気候関連開示要件",
        "source": "TSE Climate Disclosure Requirements",
    },
]

# Mock KB — iais_ins_climate namespace (TCFD Insurance Working Group +
# IAIS Application Paper on Climate Risk to Insurance 2021 + IAIS
# supervisory material). This is the insurance-sector differentiator.
IAIS_INS_CLIMATE_KB = [
    {
        "category": "insurance_sector_specific",
        "provision_id": "TCFD-InsWG-Underwriting-1",
        "summary": "保険引受・保険料設定における気候リスク統合に関するTCFD保険ワーキンググループ指針",
        "source": "TCFD Insurance Working Group",
    },
    {
        "category": "iais_supervision",
        "provision_id": "IAIS-AppPaper-2021-Supervision-1",
        "summary": "気候リスクが保険会社の健全性に与える影響に関する監督上の期待",
        "source": "IAIS Application Paper on Climate Risk to Insurance (2021)",
    },
    {
        "category": "iais_supervision",
        "provision_id": "IAIS-Supervisory-Material-1",
        "summary": "保険監督者向け気候関連リスク監督ガイダンス",
        "source": "IAIS supervisory material",
    },
]


def detect_portfolio_quantification(query: str) -> bool:
    """Non-suppressible scope-advisory check: reject portfolio-specific
    climate risk quantification requests — out of scope for this
    methodology/compliance Q&A agent."""
    return bool(_PORTFOLIO_QUANT_RE.search(query or ""))


def normalize_query(user_input: str) -> tuple[str, str | None]:
    normalized = (user_input or "").strip()
    if not normalized:
        return "", "empty query"
    return normalized, None


def classify_query_category(query: str) -> str:
    lowered = query.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in query or kw in lowered for kw in keywords):
            return category
    return "disclosure_format"


def needs_insurance_overlay(category: str) -> bool:
    return category in INSURANCE_OVERLAY_CATEGORIES


def retrieve_tcfd_provisions(category: str, kb: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = [item for item in kb if item.get("category") == category]
    return matches or [item for item in kb if item.get("category") == "disclosure_format"][:1]


def retrieve_iais_provisions(category: str, kb: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in kb if item.get("category") == category]


def compose_answer(
    category: str,
    tcfd_provisions: list[dict[str, Any]],
    iais_provisions: list[dict[str, Any]],
    tcfd_recommendation_version: str,
    fsa_guidance_vintage: str,
) -> tuple[str, list[str], str, str, list[str]]:
    """Return (answer_text, scenario_applicable, disclosure_format_guidance,
    methodology_citation, kb_source_ref)."""
    citations = [
        f"{p.get('provision_id', '')} — {p.get('summary', '')} ({p.get('source', '')})" for p in tcfd_provisions
    ]
    citations.extend(
        f"{p.get('provision_id', '')} — {p.get('summary', '')} ({p.get('source', '')})" for p in iais_provisions
    )
    kb_source_ref = [p.get("provision_id", "") for p in (*tcfd_provisions, *iais_provisions)]

    methodology_citation = f"TCFD Recommendations v{tcfd_recommendation_version}; FSA Guidance {fsa_guidance_vintage}"
    if iais_provisions:
        methodology_citation += "; IAIS Application Paper on Climate Risk to Insurance (2021)"

    scenario_applicable = ["1.5C", "2C", "4C"] if category == "scenario_analysis" else []

    disclosure_format_guidance = (
        "TCFD 4-pillar structure (Governance / Strategy / Risk Management / Metrics & Targets); "
        "align with FSA/TSE climate-disclosure item list"
        if category == "disclosure_format"
        else ""
    )

    prefix = "【保険セクター】" if iais_provisions else "【TCFD手法】"
    body = "; ".join(citations) if citations else "該当する条文が見つかりませんでした。"
    answer_text = f"{prefix}{body} [{methodology_citation}]"

    return answer_text, scenario_applicable, disclosure_format_guidance, methodology_citation, kb_source_ref
