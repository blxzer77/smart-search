from typing import Any


SOURCE_PROVENANCE_WARNING = (
    "extra_sources are retrieved in parallel and are not automatically used to verify generated content; "
    "use fetch on key URLs for claim-level evidence."
)
MINIMUM_PROFILE_ERROR = (
    "最低配置不满足：必须至少配置 main_search、docs_search、web_fetch 三类能力各一个 provider。"
)
OPENAI_COMPATIBLE_DIAGNOSE_COMMAND = "smart-search diagnose openai-compatible --format markdown"
XAI_DIAGNOSE_COMMAND = "smart-search diagnose xai --format markdown"

# Strong cues alone can mark docs/API intent (precision-first).
DOCS_INTENT_ASCII_STRONG = {
    "api",
    "sdk",
    "library",
    "framework",
    "docs",
    "documentation",
    "reference",
    "guide",
    "tutorial",
    "quickstart",
    "example",
    "examples",
    "usage",
    "manual",
    "changelog",
    "release notes",
    "migration",
    "syntax",
}
# Weak product/language tokens need a strong secondary cue (or allowlist pair).
DOCS_INTENT_ASCII_WEAK = {
    "react",
    "next.js",
    "vue",
    "python",
    "prisma",
    "langchain",
    "openai",
    "fastapi",
}
DOCS_INTENT_ASCII_KEYWORDS = DOCS_INTENT_ASCII_STRONG | DOCS_INTENT_ASCII_WEAK
RESEARCH_PROVIDER_MENTION_KEYWORDS = {
    "tavily",
    "exa",
    "context7",
    "firecrawl",
    "jina",
    "openai-compatible",
    "openai compatible",
}
RESEARCH_BROAD_TOPIC_KEYWORDS = {
    "best practices",
    "best-practices",
    "architecture patterns",
    "architecture pattern",
    "workflow",
    "tooling",
    "agent tools",
    "agent tool",
    "compare",
    "comparison",
    "benchmark",
    "landscape",
    "vs",
    "versus",
    "better",
    "rag",
    "对比",
    "架构",
    "取舍",
    "选型",
    "哪个好",
    "更好",
    "2024",
    "2025",
    "2026",
}
DOCS_INTENT_TEXT_STRONG = {
    "接口",
    "文档",
    "框架",
    "函数",
    "教程",
    "指南",
    "示例",
    "用法",
    "快速开始",
    "迁移",
    "变更日志",
    "版本说明",
}
DOCS_INTENT_TEXT_WEAK = {
    "库",
    "参数",
    "配置",
}
DOCS_INTENT_TEXT_KEYWORDS = DOCS_INTENT_TEXT_STRONG | DOCS_INTENT_TEXT_WEAK
# Terse but legitimate docs questions: weak token + any of these companions.
DOCS_INTENT_TERSE_PAIRS: tuple[tuple[str, frozenset[str]], ...] = (
    ("python", frozenset({"syntax", "comprehension", "typing", "asyncio", "decorator", "generator"})),
    ("react", frozenset({"hook", "hooks", "jsx", "component", "useeffect", "usestate"})),
)
DOCS_INTENT_KEYWORDS = DOCS_INTENT_ASCII_KEYWORDS | DOCS_INTENT_TEXT_KEYWORDS
ZH_CURRENT_KEYWORDS = {
    "今天",
    "最新",
    "国内",
    "中国",
    "政策",
    "新闻",
    "实时",
    "刚刚",
    "本周",
    "本月",
    "战报",
    "比分",
    "赛程",
    "赛果",
    "季后赛",
    "比赛",
    "nba",
    "足球",
    "篮球",
}
FETCH_INTENT_KEYWORDS = {"http://", "https://"}
DEEP_ALLOWED_TOOLS = {
    "search",
    "exa-search",
    "exa-similar",
    "context7-library",
    "context7-docs",
    "fetch",
    "map",
}
DEEP_TRIGGER_KEYWORDS = {
    "深度搜索",
    "深度调研",
    "深入搜索",
    "deep search",
    "deep research",
    "核验",
    "验证",
    "交叉验证",
    "选型",
    "对比",
    "评测",
}
DEEP_HIGH_COMPLEXITY_KEYWORDS = {
    "对比",
    "选型",
    "核验",
    "验证",
    "为什么",
    "架构",
    "方案",
    "趋势",
    "优缺点",
    "风险",
    "区别",
    "怎么选",
    "compare",
    "comparison",
    "evaluate",
    "architecture",
    "tradeoff",
    "trade-off",
    "risk",
}
DEEP_RECENT_KEYWORDS = {
    "最近",
    "最新",
    "当前",
    "现在",
    "今天",
    "实时",
    "刚刚",
    "本周",
    "本月",
    "recent",
    "latest",
    "current",
    "today",
}
DEEP_CURRENT_KEYWORDS = {"今天", "实时", "刚刚", "当前", "现在", "today", "current", "live", "realtime"}
DEEP_CHINA_KEYWORDS = {"中国", "国内", "中文", "政策", "监管", "公告", "A股", "港股"}
DEEP_EXA_DISCOVERY_KEYWORDS = {
    "官方",
    "官网",
    "论文",
    "paper",
    "papers",
    "research paper",
    "产品页",
    "product page",
    "可信站点",
    "trusted",
    "known domain",
    "known domains",
    "site:",
    "白皮书",
    "standard",
    "standards",
}
RESEARCH_ROUTE_POLICY_VERSION = "research-router-v3-intent-p0"
RESEARCH_JS_HEAVY_KEYWORDS = {
    "js-heavy",
    "javascript",
    "dynamic",
    "动态页面",
    "浏览器渲染",
    "登录页",
    "cloudflare",
    "screenshot",
    "ocr",
    "扫描",
}
RESEARCH_PDF_KEYWORDS = {"pdf", "arxiv", "论文", "paper", ".pdf"}
RESEARCH_PROFILE_ORDER = {
    "main_search": ["xai-responses", "openai-compatible"],
    "web_search": ["tavily", "firecrawl"],
    "docs_search": ["context7", "exa"],
    "web_fetch": ["tavily", "jina", "firecrawl"],
    "site_map": ["tavily"],
    "synthesis": ["main-search"],
}
PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "xai-responses": {
        "capability": "main_search",
        "strengths": ["broad synthesis", "web_search", "x_search"],
        "exclusions": ["evidence proof without fetch"],
        "fallback_group": "main_search",
        "minimum_profile_role": "main_search",
        "quality_filters": ["source extraction required for high-risk claims"],
        "route_reasons": ["primary synthesis with xAI server-side web/x search"],
    },
    "openai-compatible": {
        "capability": "main_search",
        "strengths": ["broad synthesis", "relay compatibility"],
        "exclusions": ["xAI server tools"],
        "fallback_group": "main_search",
        "minimum_profile_role": "main_search",
        "quality_filters": ["source extraction required for high-risk claims"],
        "route_reasons": ["relay-compatible primary synthesis"],
    },
    "context7": {
        "capability": "docs_search",
        "strengths": ["library docs", "API docs", "framework docs", "versioned snippets"],
        "exclusions": ["general news", "generic web facts"],
        "fallback_group": "docs_search",
        "minimum_profile_role": "docs_search",
        "quality_filters": ["library id required", "content required before citation"],
        "route_reasons": ["docs/API evidence", "framework reference"],
    },
    "exa": {
        "capability": "docs_search",
        "strengths": ["official domains", "papers", "product pages", "trusted low-noise discovery", "similar pages"],
        "exclusions": ["default second hop for every high-risk claim"],
        "fallback_group": "docs_search",
        "minimum_profile_role": "docs_search",
        "quality_filters": ["URL required", "fetch before proof citation"],
        "route_reasons": ["official low-noise discovery", "paper/product discovery"],
    },
    "tavily": {
        "capability": "web_search",
        "capabilities": ["web_search", "web_fetch", "site_map"],
        "strengths": ["broad source discovery", "site map", "URL extract"],
        "exclusions": ["docs semantic replacement"],
        "fallback_group": "web_search/web_fetch/site_map",
        "minimum_profile_role": "web_fetch",
        "quality_filters": ["non-empty normalized result", "non-empty extracted content"],
        "route_reasons": ["broad source discovery", "site map", "URL fetch"],
    },
    "jina": {
        "capability": "web_fetch",
        "strengths": ["known public URL", "PDF", "arXiv", "clean markdown", "ReaderLM-v2 with key"],
        "exclusions": ["general search provider", "anonymous standard minimum profile"],
        "fallback_group": "web_fetch",
        "minimum_profile_role": "web_fetch_with_key",
        "quality_filters": ["non-empty markdown", "challenge page rejection", "ReaderLM-v2 requires key"],
        "route_reasons": ["known URL extraction", "PDF/arXiv extraction"],
    },
    "firecrawl": {
        "capability": "web_fetch",
        "capabilities": ["web_search", "web_fetch"],
        "strengths": ["robust scrape fallback", "JS-heavy pages", "dynamic pages", "OCR/PDF/structured extraction"],
        "exclusions": ["docs semantic replacement"],
        "fallback_group": "web_search/web_fetch",
        "minimum_profile_role": "web_fetch",
        "quality_filters": ["non-empty normalized result", "non-empty extracted content"],
        "route_reasons": ["JS-heavy fetch", "dynamic/browser-like extraction", "robust fetch fallback"],
    },
    "main-search": {
        "capability": "synthesis",
        "strengths": ["evidence-only final synthesis"],
        "exclusions": ["live source discovery during research synthesis"],
        "fallback_group": "synthesis",
        "minimum_profile_role": "",
        "quality_filters": ["fetched evidence only", "no provider calls during synthesis"],
        "route_reasons": ["evidence-only synthesis"],
    },
}
MAIN_SEARCH_FALLBACK_CHAIN = ["xai-responses", "openai-compatible"]
MAIN_SEARCH_PROVIDER_ALIASES = {
    "xai-responses": {"xai-responses", "xai", "grok", "grok-web-tools"},
    "openai-compatible": {"openai-compatible", "openai", "chat-completions", "primary"},
}
