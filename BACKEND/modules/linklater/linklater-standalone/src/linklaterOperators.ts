export type LinklaterEntityType =
  | "all"
  | "person"
  | "company"
  | "email"
  | "phone"
  | "address"
  | "username";

export type LinklaterHistoryMode = "single" | "range" | "before" | "all";

export type LinklaterAction =
  | "discover"
  | "page-scrape"
  | "deep-crawl"
  | "enrich-all"
  | "full-enrich"
  | "backlinks-domains"
  | "backlinks-pages"
  | "backlinks-host"
  | "backlinks-cc"
  | "backlinks-global"
  | "backlinks-majestic"
  | "backlink-archive"
  | "backlink-temporal"
  | "outlinks-domains"
  | "outlinks-pages"
  | "outlinks-cc"
  | "entities"
  | "filetype"
  | "archive-keyword"
  | "archive-changes"
  | "archive-diff"
  | "wayback"
  | "whois"
  | "ssl"
  | "dns"
  | "subdomains"
  | "tech"
  | "ga"
  | "ga-related"
  | "sitemap"
  | "map-domain"
  | "cc-index"
  | "search-engines"
  | "metadata"
  | "cc-mime"
  | "schema"
  | "dehashed"
  | "link-neighbors"
  | "link-hop"
  | "related-nameservers"
  | "related-cohosted"
  | "related-majestic"
  | "news"
  | "social"
  | "breach"
  | "link-velocity"
  | "corpus-domain"
  | "corpus-search";

export interface LinklaterHistory {
  mode: LinklaterHistoryMode;
  raw: string;
  startYear?: string;
  endYear?: string;
}

export interface ParsedLinklaterQuery {
  raw: string;
  action: LinklaterAction;
  domain?: string;
  targetUrl?: string;
  keyword?: string;
  filetypes?: string[];
  entityType?: LinklaterEntityType;
  archiveDirection?: "forward" | "backward" | "both" | "live";
  history?: LinklaterHistory;
}

const PREFIX_OPERATORS = new Set([
  "whois",
  "age",
  "dns",
  "subdomains",
  "subdomain",
  "tech",
  "ga",
  "sitemap",
  "backlinks",
  "backlink",
  "outlinks",
  "outlink",
  "wayback",
  "archive",
  "corpus",
  "extract",
  "enrich",
  "full",
  "map",
  "map-domain",
  "crawl",
  "deep-crawl",
  "ccindex",
  "cc-index",
  "engines",
  "search-engines",
  "meta",
  "metadata",
  "mime",
  "cc-mime",
  "schema",
  "schemaorg",
  "schema-org",
  "dehashed",
  "hostgraph",
  "backlinks-host",
  "ccgraph",
  "backlinks-cc",
  "globallinks",
  "backlinks-global",
  "majestic-backlinks",
  "neighbors",
  "link-neighbors",
  "backlink-archive",
  "temporal-backlinks",
  "backlink-temporal",
  "outlinks-cc",
  "ccoutlinks",
  "cc-outlinks",
  "nameservers",
  "cohosted",
  "majestic-related",
  "related-majestic",
  "ga-related",
  "link-hop",
  "ssl",
  "archive-changes",
  "archive-diff",
  "news",
  "social",
  "breach",
  "links-velocity",
  "link-velocity",
  "velocity",
]);

const LINK_OPERATORS = new Set([
  "?bl",
  "bl?",
  "!bl",
  "bl!",
  "?ol",
  "ol?",
  "!ol",
  "ol!",
  "ent?",
  "ent!",
  "p?",
  "p!",
  "c?",
  "c!",
  "t?",
  "t!",
  "e?",
  "e!",
  "a?",
  "a!",
  "u?",
  "u!",
]);

const FILETYPE_OPERATORS = new Set([
  "pdf!",
  "doc!",
  "word!",
  "xls!",
  "ppt!",
  "file!",
]);

const FILETYPE_MAP: Record<string, string[]> = {
  "pdf!": ["pdf"],
  "doc!": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"],
  "file!": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"],
  "word!": ["doc", "docx", "odt", "rtf"],
  "xls!": ["xls", "xlsx", "ods", "csv"],
  "ppt!": ["ppt", "pptx", "odp"],
};

function extractDomain(raw: string): string | null {
  let value = raw.trim();
  value = value.replace(/^https?:\/\//i, "");
  value = value.replace(/^www\./i, "");
  const match = value.match(/^([^/\s?#:]+)/);
  if (!match) return null;
  return match[1].toLowerCase();
}

function normalizeUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return trimmed;
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function looksLikeDomain(raw: string): boolean {
  const value = raw.trim().replace(/^https?:\/\//i, "");
  return /[a-z0-9-]+\.[a-z]{2,}/i.test(value);
}

function parseHistory(raw: string): { history?: LinklaterHistory; rest: string } {
  const trimmed = raw.trim();
  const match = trimmed.match(/^(<-!?|\d{4}(?:-\d{4})?)!\s+(.*)$/);
  if (!match) {
    return { rest: trimmed };
  }

  const token = match[1];
  const rest = match[2];
  if (token === "<-" || token === "<-!") {
    return {
      rest,
      history: {
        mode: "all",
        raw: token,
      },
    };
  }

  if (token.startsWith("<-")) {
    return {
      rest,
      history: {
        mode: "before",
        raw: token,
        endYear: token.replace("<-", ""),
      },
    };
  }

  if (token.includes("-")) {
    const [startYear, endYear] = token.split("-");
    return {
      rest,
      history: {
        mode: "range",
        raw: token,
        startYear,
        endYear,
      },
    };
  }

  return {
    rest,
    history: {
      mode: "single",
      raw: token,
      startYear: token,
      endYear: token,
    },
  };
}

function parseTarget(rawTarget: string): {
  domain?: string;
  targetUrl?: string;
  scope: "domain" | "page";
  archiveDirection?: "forward" | "backward" | "both" | "live";
  history?: LinklaterHistory;
} {
  let target = rawTarget.trim();

  let archiveDirection: "forward" | "backward" | "both" | "live" | undefined;
  if (target.startsWith("-><-")) {
    archiveDirection = "both";
    target = target.slice(4).trim();
  } else if (target.startsWith("->")) {
    archiveDirection = "forward";
    target = target.slice(2).trim();
  } else if (target.startsWith("<-")) {
    archiveDirection = "backward";
    target = target.slice(2).trim();
  } else if (target.startsWith("?")) {
    archiveDirection = "live";
    target = target.slice(1).trim();
  }

  const { history, rest } = parseHistory(target);
  target = rest;

  let scope: "domain" | "page" = "domain";
  if (target.startsWith("!")) {
    target = target.slice(1).trim();
    scope = "domain";
  } else if (target.endsWith("!")) {
    target = target.slice(0, -1).trim();
    scope = "page";
  } else if (target.endsWith("?")) {
    target = target.slice(0, -1).trim();
    scope = "page";
  }

  const domain = extractDomain(target);
  const targetUrl = scope === "page" ? normalizeUrl(target) : undefined;

  return {
    domain: domain || undefined,
    targetUrl,
    scope,
    archiveDirection,
    history,
  };
}

function isLinklaterTarget(rawTarget: string): boolean {
  const trimmed = rawTarget.trim();
  if (/^(-><-|->|<-|\?)/.test(trimmed)) return true;
  if (trimmed.includes("!")) return true;
  return looksLikeDomain(trimmed);
}

function splitTargetAndKeyword(raw: string): { target: string; keyword?: string } {
  const trimmed = raw.trim();
  if (!trimmed) return { target: "" };
  const match = trimmed.match(/^(\S+)(?:\s+(.+))?$/);
  if (!match) return { target: trimmed };
  return {
    target: match[1],
    keyword: match[2]?.trim() || undefined,
  };
}

export function parseLinklaterQuery(raw: string): ParsedLinklaterQuery | null {
  const trimmed = String(raw || "").trim();
  if (!trimmed) return null;
  if (trimmed.includes("=>") || trimmed.includes("::")) return null;

  if (!trimmed.includes(":") && trimmed.startsWith("?")) {
    const domain = extractDomain(trimmed.slice(1));
    if (!domain) return null;
    return {
      raw: trimmed,
      action: "discover",
      domain,
    };
  }

  if (!trimmed.includes(":") && trimmed.startsWith("!")) {
    const targetInfo = parseTarget(trimmed);
    if (!targetInfo.domain) return null;
    return {
      raw: trimmed,
      action: "deep-crawl",
      domain: targetInfo.domain,
      targetUrl: targetInfo.targetUrl,
    };
  }

  if (!trimmed.includes(":") && (trimmed.endsWith("?") || trimmed.endsWith("!"))) {
    const targetInfo = parseTarget(trimmed);
    if (!targetInfo.domain) return null;
    return {
      raw: trimmed,
      action: "page-scrape",
      domain: targetInfo.domain,
      targetUrl: targetInfo.targetUrl,
    };
  }

  const colonIndex = trimmed.indexOf(":");
  if (colonIndex === -1) return null;

  const left = trimmed.slice(0, colonIndex).trim();
  const right = trimmed.slice(colonIndex + 1).trim();
  if (!left || !right) return null;

  const leftLower = left.toLowerCase();
  const leftNormalized = leftLower.endsWith("!") ? leftLower.slice(0, -1) : leftLower;

  if (PREFIX_OPERATORS.has(leftNormalized)) {
    if (
      leftNormalized === "archive" ||
      leftNormalized === "corpus" ||
      leftNormalized === "enrich" ||
      leftNormalized === "full" ||
      leftNormalized === "backlink-archive" ||
      leftNormalized === "backlink-temporal" ||
      leftNormalized === "temporal-backlinks" ||
      leftNormalized === "archive-changes" ||
      leftNormalized === "archive-diff" ||
      leftNormalized === "link-hop"
    ) {
      const { target: targetPart, keyword } = splitTargetAndKeyword(right);
      const targetInfo = parseTarget(targetPart);
      if (!targetInfo.domain) return null;

      if (leftNormalized === "archive") {
        return {
          raw: trimmed,
          action: keyword ? "archive-keyword" : "wayback",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
          archiveDirection: targetInfo.archiveDirection,
          history: targetInfo.history,
        };
      }

      if (leftNormalized === "corpus") {
        return {
          raw: trimmed,
          action: keyword ? "corpus-search" : "corpus-domain",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
        };
      }

      if (leftNormalized === "enrich") {
        return {
          raw: trimmed,
          action: keyword ? "full-enrich" : "enrich-all",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
          archiveDirection: targetInfo.archiveDirection,
          history: targetInfo.history,
        };
      }

      if (leftNormalized === "full") {
        return {
          raw: trimmed,
          action: "full-enrich",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
          archiveDirection: targetInfo.archiveDirection,
          history: targetInfo.history,
        };
      }

      if (leftNormalized === "backlink-archive") {
        return {
          raw: trimmed,
          action: "backlink-archive",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
        };
      }

      if (leftNormalized === "backlink-temporal" || leftNormalized === "temporal-backlinks") {
        return {
          raw: trimmed,
          action: "backlink-temporal",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
        };
      }

      if (leftNormalized === "archive-changes") {
        return {
          raw: trimmed,
          action: "archive-changes",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
        };
      }

      if (leftNormalized === "archive-diff") {
        return {
          raw: trimmed,
          action: "archive-diff",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
        };
      }

      if (leftNormalized === "link-hop") {
        return {
          raw: trimmed,
          action: "link-hop",
          domain: targetInfo.domain,
          targetUrl: targetInfo.targetUrl,
          keyword,
        };
      }

      return {
        raw: trimmed,
        action: "full-enrich",
        domain: targetInfo.domain,
        targetUrl: targetInfo.targetUrl,
        keyword,
        archiveDirection: targetInfo.archiveDirection,
        history: targetInfo.history,
      };
    }

    const targetInfo = parseTarget(right);
    if (!targetInfo.domain) return null;

    const base: ParsedLinklaterQuery = {
      raw: trimmed,
      action: "full-enrich",
      domain: targetInfo.domain,
      targetUrl: targetInfo.targetUrl,
      archiveDirection: targetInfo.archiveDirection,
      history: targetInfo.history,
    };

    switch (leftNormalized) {
      case "whois":
      case "age":
        return { ...base, action: "whois" };
      case "dns":
        return { ...base, action: "dns" };
      case "subdomains":
      case "subdomain":
        return { ...base, action: "subdomains" };
      case "tech":
        return { ...base, action: "tech" };
      case "ga":
        return { ...base, action: "ga" };
      case "sitemap":
        return { ...base, action: "sitemap" };
      case "backlinks":
      case "backlink":
        return { ...base, action: "backlinks-domains" };
      case "outlinks":
      case "outlink":
        return { ...base, action: "outlinks-domains" };
      case "wayback":
        return { ...base, action: "wayback" };
      case "extract":
        return { ...base, action: "entities", entityType: "all" };
      case "map":
      case "map-domain":
        return { ...base, action: "map-domain" };
      case "crawl":
      case "deep-crawl":
        return { ...base, action: "deep-crawl" };
      case "ccindex":
      case "cc-index":
        return { ...base, action: "cc-index" };
      case "engines":
      case "search-engines":
        return { ...base, action: "search-engines" };
      case "meta":
      case "metadata":
        return { ...base, action: "metadata" };
      case "mime":
      case "cc-mime":
        return { ...base, action: "cc-mime" };
      case "schema":
      case "schemaorg":
      case "schema-org":
        return { ...base, action: "schema" };
      case "dehashed":
        return { ...base, action: "dehashed" };
      case "hostgraph":
      case "backlinks-host":
        return { ...base, action: "backlinks-host" };
      case "ccgraph":
      case "backlinks-cc":
        return { ...base, action: "backlinks-cc" };
      case "globallinks":
      case "backlinks-global":
        return { ...base, action: "backlinks-global" };
      case "majestic-backlinks":
        return { ...base, action: "backlinks-majestic" };
      case "neighbors":
      case "link-neighbors":
        return { ...base, action: "link-neighbors" };
      case "outlinks-cc":
      case "ccoutlinks":
      case "cc-outlinks":
        return { ...base, action: "outlinks-cc" };
      case "nameservers":
        return { ...base, action: "related-nameservers" };
      case "cohosted":
        return { ...base, action: "related-cohosted" };
      case "majestic-related":
      case "related-majestic":
        return { ...base, action: "related-majestic" };
      case "ga-related":
        return { ...base, action: "ga-related" };
      case "ssl":
        return { ...base, action: "ssl" };
      case "news":
        return { ...base, action: "news" };
      case "social":
        return { ...base, action: "social" };
      case "breach":
        return { ...base, action: "breach" };
      case "links-velocity":
      case "link-velocity":
      case "velocity":
        return { ...base, action: "link-velocity" };
      default:
        return null;
    }
  }

  if (LINK_OPERATORS.has(leftLower)) {
    const targetInfo = parseTarget(right);
    if (!targetInfo.domain) return null;

    if (leftLower === "?bl" || leftLower === "!bl") {
      return {
        raw: trimmed,
        action: "backlinks-domains",
        domain: targetInfo.domain,
        targetUrl: targetInfo.targetUrl,
        archiveDirection: targetInfo.archiveDirection,
        history: targetInfo.history,
      };
    }
    if (leftLower === "bl?" || leftLower === "bl!") {
      return {
        raw: trimmed,
        action: "backlinks-pages",
        domain: targetInfo.domain,
        targetUrl: targetInfo.targetUrl,
        archiveDirection: targetInfo.archiveDirection,
        history: targetInfo.history,
      };
    }
    if (leftLower === "?ol" || leftLower === "!ol") {
      return {
        raw: trimmed,
        action: "outlinks-domains",
        domain: targetInfo.domain,
        targetUrl: targetInfo.targetUrl,
      };
    }
    if (leftLower === "ol?" || leftLower === "ol!") {
      return {
        raw: trimmed,
        action: "outlinks-pages",
        domain: targetInfo.domain,
        targetUrl: targetInfo.targetUrl,
      };
    }

    const entityTypeMap: Record<string, LinklaterEntityType> = {
      "ent?": "all",
      "ent!": "all",
      "p?": "person",
      "p!": "person",
      "c?": "company",
      "c!": "company",
      "t?": "phone",
      "t!": "phone",
      "e?": "email",
      "e!": "email",
      "a?": "address",
      "a!": "address",
      "u?": "username",
      "u!": "username",
    };

    return {
      raw: trimmed,
      action: "entities",
      domain: targetInfo.domain,
      targetUrl: targetInfo.targetUrl,
      entityType: entityTypeMap[leftLower] || "all",
      archiveDirection: targetInfo.archiveDirection,
      history: targetInfo.history,
    };
  }

  if (FILETYPE_OPERATORS.has(leftLower)) {
    const targetInfo = parseTarget(right);
    if (!targetInfo.domain) return null;
    return {
      raw: trimmed,
      action: "filetype",
      domain: targetInfo.domain,
      targetUrl: targetInfo.targetUrl,
      filetypes: FILETYPE_MAP[leftLower] || [],
    };
  }

  if (!isLinklaterTarget(right)) return null;
  const targetInfo = parseTarget(right);
  if (!targetInfo.domain) return null;

  if (targetInfo.archiveDirection && targetInfo.archiveDirection !== "live") {
    return {
      raw: trimmed,
      action: "archive-keyword",
      domain: targetInfo.domain,
      targetUrl: targetInfo.targetUrl,
      keyword: left,
      archiveDirection: targetInfo.archiveDirection,
    };
  }

  return {
    raw: trimmed,
    action: "full-enrich",
    domain: targetInfo.domain,
    targetUrl: targetInfo.targetUrl,
    keyword: left,
    archiveDirection: targetInfo.archiveDirection,
  };
}

export function isLinklaterOperatorQuery(raw: string): boolean {
  return Boolean(parseLinklaterQuery(raw));
}
