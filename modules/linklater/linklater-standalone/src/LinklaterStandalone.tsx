import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Archive,
  BarChart3,
  Database,
  ExternalLink,
  FileText,
  Globe,
  Link2,
  Loader2,
  Map as MapIcon,
  Network,
  RefreshCw,
  Search,
  Server,
  Shield,
  Sparkles,
  Users,
} from "lucide-react";
import { parseLinklaterQuery, type LinklaterAction } from "./linklaterOperators";

type ViewMode = "formatted" | "raw";
type SectionMode = "enrichment" | "discovery";

type ActionStatus = "idle" | "loading" | "success" | "error";

interface ResultItem {
  id: string;
  title: string;
  subtitle?: string;
  url?: string;
  tags?: string[];
  meta?: Record<string, string | number>;
}

interface ActionResult {
  status: ActionStatus;
  summary?: string;
  items?: ResultItem[];
  raw?: any;
  error?: string;
  updatedAt?: string;
}

interface GraphNode {
  id: string;
  label: string;
  kind: string;
  subtype?: string;
  meta?: Record<string, string | number>;
}

interface GraphEdge {
  id: string;
  from: string;
  to: string;
  relation: string;
}

const INPUT_CLASS =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors";

const BUTTON_STANDARD =
  "border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:text-slate-900";

const BUTTON_PRIMARY =
  "border-slate-900 bg-slate-900 text-white hover:border-slate-800 hover:bg-slate-800";

const BUTTON_ENTITY =
  "border-emerald-600 bg-emerald-600 text-white hover:border-emerald-700 hover:bg-emerald-700";

const BUTTON_SUBTLE =
  "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:text-slate-700";

const CHIP_BASE = "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium";

const ENTITY_CHIP = "border-emerald-200 bg-emerald-50 text-emerald-700";
const DOMAIN_CHIP = "border-slate-200 bg-white text-slate-600";
const URL_CHIP = "border-blue-200 bg-blue-50 text-blue-700";
const TRACKER_CHIP = "border-amber-200 bg-amber-50 text-amber-700";
const TECH_CHIP = "border-indigo-200 bg-indigo-50 text-indigo-700";

const MAX_GRAPH_NODES = 120;

const toDomain = (raw: string) => {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const withoutProtocol = trimmed.replace(/^https?:\/\//i, "").replace(/^www\./i, "");
  return withoutProtocol.split("/")[0].toLowerCase();
};

const toUrl = (raw: string) => {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
};

const extractDomainFromUrl = (raw: string) => {
  try {
    const url = new URL(raw);
    return url.hostname.replace(/^www\./i, "").toLowerCase();
  } catch {
    return toDomain(raw);
  }
};

const makeId = (kind: string, value: string) => {
  const safeValue = encodeURIComponent(value.toLowerCase());
  return `${kind}:${safeValue}`;
};

const createNode = (kind: string, label: string, subtype?: string, meta?: Record<string, string | number>): GraphNode => ({
  id: makeId(kind, label),
  label,
  kind,
  subtype,
  meta,
});

const createEdge = (from: string, to: string, relation: string): GraphEdge => ({
  id: `${from}|${relation}|${to}`,
  from,
  to,
  relation,
});

const dedupeItems = (items: ResultItem[]) => {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = item.id || item.title;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

const extractMetadataFromHtml = (html: string) => {
  if (!html || typeof DOMParser === "undefined") return {} as Record<string, string>;
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const title = doc.querySelector("title")?.textContent?.trim();
    const description =
      doc.querySelector('meta[name="description"]')?.getAttribute("content")?.trim() ||
      doc.querySelector('meta[property="og:description"]')?.getAttribute("content")?.trim();
    const canonical = doc.querySelector('link[rel="canonical"]')?.getAttribute("href")?.trim();
    const language = doc.documentElement?.getAttribute("lang")?.trim();

    const og: Record<string, string> = {};
    doc.querySelectorAll('meta[property^="og:"]').forEach((meta) => {
      const prop = meta.getAttribute("property")?.replace(/^og:/i, "");
      const content = meta.getAttribute("content")?.trim();
      if (prop && content) og[prop] = content;
    });

    return {
      title: title || "",
      description: description || "",
      canonical: canonical || "",
      language: language || "",
      og: Object.keys(og).length ? JSON.stringify(og) : "",
    };
  } catch {
    return {} as Record<string, string>;
  }
};

const extractJsonLd = (html: string) => {
  if (!html || typeof DOMParser === "undefined") return [] as any[];
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const scripts = Array.from(doc.querySelectorAll('script[type="application/ld+json"]'));
    const results: any[] = [];
    scripts.forEach((script) => {
      const raw = script.textContent || "";
      if (!raw.trim()) return;
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          results.push(...parsed);
        } else {
          results.push(parsed);
        }
      } catch {
        return;
      }
    });
    return results;
  } catch {
    return [] as any[];
  }
};

const parseArchiveKeywordInput = (raw: string, mode: "semantic" | "exact" | "variation") => {
  const exactRegex = /"([^"]+)"/g;
  const variationRegex = /'([^']+)'/g;
  const exactPhrases = Array.from(raw.matchAll(exactRegex))
    .map((match) => match[1].trim())
    .filter(Boolean);
  const variationPhrases = Array.from(raw.matchAll(variationRegex))
    .map((match) => match[1].trim())
    .filter(Boolean);
  const stripped = raw.replace(exactRegex, " ").replace(variationRegex, " ");
  let leftover = stripped.replace(/\s+/g, " ").trim();

  if (exactPhrases.length === 0 && variationPhrases.length === 0 && leftover) {
    if (mode === "exact") {
      exactPhrases.push(leftover);
      leftover = "";
    } else if (mode === "variation") {
      variationPhrases.push(leftover);
      leftover = "";
    }
  }

  return { exactPhrases, variationPhrases, leftover };
};

const formatArchiveOperatorKeyword = (raw: string, mode: "semantic" | "exact" | "variation") => {
  const trimmed = raw.trim();
  if (!trimmed) return trimmed;
  if (/"[^"]+"|'[^']+'/.test(trimmed)) return trimmed;
  if (mode === "exact") return `"${trimmed}"`;
  if (mode === "variation") return `'${trimmed}'`;
  return trimmed;
};

const normalizeArchiveKeywordForMode = (raw: string, mode: "semantic" | "exact" | "variation") => {
  const trimmed = raw.trim();
  if (!trimmed) return trimmed;
  const unwrapped =
    (trimmed.startsWith("\"") && trimmed.endsWith("\"")) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
      ? trimmed.slice(1, -1).trim()
      : trimmed;
  if (mode === "exact") return `"${unwrapped}"`;
  if (mode === "variation") return `'${unwrapped}'`;
  return unwrapped;
};

const SectionHeader = ({
  title,
  description,
  icon: Icon,
}: {
  title: string;
  description?: string;
  icon: React.ElementType;
}) => (
  <div className="flex items-start gap-3">
    <div className="rounded-xl border border-slate-200 bg-white p-2 text-slate-600 shadow-sm">
      <Icon className="h-5 w-5" />
    </div>
    <div>
      <div className="text-lg font-semibold text-slate-900">{title}</div>
      {description && <div className="text-sm text-slate-500">{description}</div>}
    </div>
  </div>
);

const ActionCard = ({
  title,
  description,
  icon: Icon,
  tone = "standard",
  runLabel = "Run",
  onRun,
  syntax,
  onUseSyntax,
  viewMode,
  result,
  children,
}: {
  title: string;
  description: string;
  icon: React.ElementType;
  tone?: "standard" | "entity";
  runLabel?: string;
  onRun: () => void;
  syntax?: string;
  onUseSyntax?: () => void;
  viewMode: ViewMode;
  result?: ActionResult;
  children?: React.ReactNode;
}) => {
  const buttonTone = tone === "entity" ? BUTTON_ENTITY : BUTTON_STANDARD;
  const isLoading = result?.status === "loading";

  return (
    <div className="animate-fade-up rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div className="flex items-start gap-3">
          <div className="rounded-xl border border-slate-100 bg-slate-50 p-2 text-slate-600">
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900">{title}</div>
            <div className="text-xs text-slate-500">{description}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {syntax && (
            <button
              type="button"
              onClick={onUseSyntax}
              className={`${BUTTON_BASE} ${BUTTON_SUBTLE}`}
            >
              Use Syntax
            </button>
          )}
          <button
            type="button"
            onClick={onRun}
            className={`${BUTTON_BASE} ${buttonTone}`}
            disabled={isLoading}
          >
            {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {runLabel}
          </button>
        </div>
      </div>
      <div className="space-y-3 px-4 py-4">
        {syntax && (
          <div className="text-xs text-slate-500">
            Syntax: <span className="font-mono text-slate-700">{syntax}</span>
          </div>
        )}
        {children}
        <ActionResultView viewMode={viewMode} result={result} />
      </div>
    </div>
  );
};

const ActionResultView = ({ viewMode, result }: { viewMode: ViewMode; result?: ActionResult }) => {
  if (!result || result.status === "idle") {
    return <div className="text-xs text-slate-400">No results yet.</div>;
  }

  if (result.status === "loading") {
    return <div className="text-xs text-slate-400">Running...</div>;
  }

  if (result.status === "error") {
    return <div className="text-xs text-red-600">{result.error || "Failed"}</div>;
  }

  if (viewMode === "raw") {
    return (
      <pre className="max-h-64 overflow-auto rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs text-slate-700">
        {JSON.stringify(result.raw ?? {}, null, 2)}
      </pre>
    );
  }

  const items = result.items || [];
  const deduped = dedupeItems(items).slice(0, 80);

  const chipClassFor = (value: string) => {
    if (value.includes("@")) return ENTITY_CHIP;
    if (value.startsWith("http")) return URL_CHIP;
    if (value.includes(".")) return DOMAIN_CHIP;
    return ENTITY_CHIP;
  };

  return (
    <div className="space-y-2">
      {result.summary && <div className="text-xs text-slate-500">{result.summary}</div>}
      {deduped.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {deduped.slice(0, 12).map((item) => (
            <span key={`chip-${item.id}`} className={`${CHIP_BASE} ${chipClassFor(item.title)}`}>
              {item.title}
            </span>
          ))}
        </div>
      )}
      {deduped.length === 0 ? (
        <div className="text-xs text-slate-400">No items.</div>
      ) : (
        deduped.map((item) => (
          <div key={item.id} className="rounded-lg border border-slate-100 bg-white p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-sm font-medium text-slate-900">{item.title}</div>
                {item.subtitle && <div className="text-xs text-slate-500">{item.subtitle}</div>}
              </div>
              {item.url && (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-slate-500 hover:text-slate-700"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
            </div>
            {item.tags && item.tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {item.tags.map((tag) => (
                  <span key={tag} className={`${CHIP_BASE} ${ENTITY_CHIP}`}>
                    {tag}
                  </span>
                ))}
              </div>
            )}
            {item.meta && Object.keys(item.meta).length > 0 && (
              <div className="mt-2 grid gap-1 text-xs text-slate-600">
                {Object.entries(item.meta).map(([key, value]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-slate-400">{key}</span>
                    <span className="truncate text-right text-slate-700">{String(value)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
};

const GraphSatellite = ({
  centerLabel,
  nodes,
  edges,
}: {
  centerLabel: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}) => {
  const filteredNodes = nodes
    .filter((node) => !centerLabel || node.label !== centerLabel)
    .slice(0, MAX_GRAPH_NODES);
  const ringA = filteredNodes.filter((node) =>
    ["entity", "tracker", "tech", "email", "phone", "nameserver"].includes(node.kind)
  );
  const ringB = filteredNodes.filter((node) => !ringA.includes(node));

  const layoutRing = (ring: GraphNode[], radius: number) => {
    return ring.map((node, index) => {
      const angle = (index / Math.max(ring.length, 1)) * Math.PI * 2;
      return {
        ...node,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      };
    });
  };

  const positionedA = layoutRing(ringA, 120);
  const positionedB = layoutRing(ringB, 210);
  const positioned = [...positionedA, ...positionedB];
  const positionMap = new Map(positioned.map((node) => [node.id, node]));

  const colorForKind = (kind: string) => {
    if (kind === "entity") return "#059669";
    if (kind === "tracker") return "#d97706";
    if (kind === "tech") return "#4f46e5";
    if (kind === "url") return "#2563eb";
    if (kind === "domain") return "#475569";
    return "#64748b";
  };

  return (
    <div className="relative h-[360px] w-full rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div
        className="absolute inset-0 rounded-2xl"
        style={{
          backgroundImage:
            "linear-gradient(rgba(148,163,184,0.12) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.12) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />
      <svg viewBox="-280 -220 560 440" className="relative h-full w-full">
        <g>
          {edges.map((edge) => {
            const from = positionMap.get(edge.from);
            const to = positionMap.get(edge.to);
            if (!from || !to) return null;
            return (
              <line
                key={edge.id}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="#cbd5f5"
                strokeWidth={1}
                opacity={0.6}
              />
            );
          })}
          {positioned.map((node) => (
            <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
              <circle r={8} fill={colorForKind(node.kind)} opacity={0.9} />
              <text
                x={12}
                y={4}
                fontSize={10}
                fill="#334155"
                fontFamily="Space Grotesk, IBM Plex Sans, sans-serif"
              >
                {node.label.slice(0, 24)}
              </text>
            </g>
          ))}
          <g>
            <circle r={18} fill="#e2e8f0" />
            <text
              x={28}
              y={5}
              fontSize={12}
              fill="#0f172a"
              fontFamily="Space Grotesk, IBM Plex Sans, sans-serif"
            >
              {centerLabel || "Target Domain"}
            </text>
          </g>
        </g>
      </svg>
    </div>
  );
};

const LinklaterStandalone: React.FC = () => {
  const [section, setSection] = useState<SectionMode>("enrichment");
  const [viewMode, setViewMode] = useState<ViewMode>("formatted");
  const [targetDomain, setTargetDomain] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [operatorQuery, setOperatorQuery] = useState("");
  const [operatorError, setOperatorError] = useState<string | null>(null);
  const [graphView, setGraphView] = useState<"relations" | "map">("relations");

  const [actionResults, setActionResults] = useState<Record<string, ActionResult>>({});
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);

  const [archiveKeyword, setArchiveKeyword] = useState("");
  const [archiveKeywordMode, setArchiveKeywordMode] = useState<"semantic" | "exact" | "variation">("semantic");
  const [archiveMaxSnapshots, setArchiveMaxSnapshots] = useState(120);
  const [archiveQuick, setArchiveQuick] = useState(true);
  const [archiveStartYear, setArchiveStartYear] = useState("2016");
  const [archiveEndYear, setArchiveEndYear] = useState("2025");
  const [archiveDiffA, setArchiveDiffA] = useState("");
  const [archiveDiffB, setArchiveDiffB] = useState("");

  const [filetypeQuery, setFiletypeQuery] = useState("pdf,doc,docx");
  const [filetypeFromYear, setFiletypeFromYear] = useState("");
  const [filetypeToYear, setFiletypeToYear] = useState("");
  const [ccMimeLimit, setCcMimeLimit] = useState(20);

  const [corpusQuery, setCorpusQuery] = useState("");
  const [corpusLimit, setCorpusLimit] = useState(50);

  const [enrichKeyword, setEnrichKeyword] = useState("");
  const [enrichUseDiscovered, setEnrichUseDiscovered] = useState(true);
  const [enrichMaxUrls, setEnrichMaxUrls] = useState(30);

  const [linkHopDirection, setLinkHopDirection] = useState<"backlinks" | "outlinks" | "both">("backlinks");
  const [linkHopDepth, setLinkHopDepth] = useState(2);
  const [linkHopMax, setLinkHopMax] = useState(12);

  const [backlinkLimit, setBacklinkLimit] = useState(200);
  const [outlinkLimit, setOutlinkLimit] = useState(200);

  const [temporalMinAge, setTemporalMinAge] = useState("");
  const [temporalMaxAge, setTemporalMaxAge] = useState("");
  const [linkVelocityDays, setLinkVelocityDays] = useState(30);

  const [discoveredUrls, setDiscoveredUrls] = useState<string[]>([]);
  const [scrapeCache, setScrapeCache] = useState<{ url: string; content: string; title?: string } | null>(null);

  const [discoveryLog, setDiscoveryLog] = useState<string[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const discoverySourceRef = useRef<EventSource | null>(null);
  const operatorDomainRef = useRef<string | null>(null);

  const targetDomainNormalized = toDomain(targetDomain);

  useEffect(() => {
    if (!targetDomainNormalized) return;
    const rootNode = createNode("domain", targetDomainNormalized);
    setGraphNodes((prev) => {
      if (prev.some((node) => node.id === rootNode.id)) return prev;
      return [rootNode, ...prev];
    });
  }, [targetDomainNormalized]);

  useEffect(() => {
    setGraphView(section === "discovery" ? "map" : "relations");
  }, [section]);

  const summaryStats = useMemo(() => {
    const stats = { domains: 0, urls: 0, entities: 0, trackers: 0, tech: 0 };
    graphNodes.forEach((node) => {
      if (node.kind === "domain") stats.domains += 1;
      if (node.kind === "url") stats.urls += 1;
      if (node.kind === "entity") stats.entities += 1;
      if (node.kind === "tracker") stats.trackers += 1;
      if (node.kind === "tech") stats.tech += 1;
    });
    return stats;
  }, [graphNodes]);

  const entityCapsules = useMemo(() => {
    return graphNodes
      .filter((node) => node.kind === "entity")
      .map((node) => node.label)
      .slice(0, 40);
  }, [graphNodes]);

  const relationNodes = useMemo(() => {
    return graphNodes.filter((node) => node.kind !== "url");
  }, [graphNodes]);

  const mapNodes = useMemo(() => {
    return graphNodes.filter((node) => node.kind === "url");
  }, [graphNodes]);

  const mergeGraph = (nodes: GraphNode[], edges: GraphEdge[]) => {
    if (nodes.length === 0 && edges.length === 0) return;
    setGraphNodes((prev) => {
      const map = new Map(prev.map((node) => [node.id, node]));
      nodes.forEach((node) => {
        const existing = map.get(node.id);
        if (!existing) {
          map.set(node.id, node);
        } else {
          map.set(node.id, {
            ...existing,
            ...node,
            meta: { ...(existing.meta || {}), ...(node.meta || {}) },
          });
        }
      });
      return Array.from(map.values());
    });
    setGraphEdges((prev) => {
      const map = new Map(prev.map((edge) => [edge.id, edge]));
      edges.forEach((edge) => {
        if (!map.has(edge.id)) map.set(edge.id, edge);
      });
      return Array.from(map.values());
    });
  };

  const updateActionResult = (id: string, patch: Partial<ActionResult>) => {
    setActionResults((prev) => ({
      ...prev,
      [id]: {
        status: "idle",
        ...(prev[id] || {}),
        ...patch,
      },
    }));
  };

  const runAction = async (id: string, label: string, runner: () => Promise<{
    items?: ResultItem[];
    raw?: any;
    nodes?: GraphNode[];
    edges?: GraphEdge[];
    summary?: string;
  }>) => {
    updateActionResult(id, { status: "loading", error: undefined });
    try {
      const payload = await runner();
      updateActionResult(id, {
        status: "success",
        items: payload.items || [],
        raw: payload.raw,
        summary: payload.summary,
        updatedAt: new Date().toISOString(),
      });
      mergeGraph(payload.nodes || [], payload.edges || []);
    } catch (error) {
      updateActionResult(id, {
        status: "error",
        error: (error as Error).message || `${label} failed`,
        raw: (error as Error).message,
      });
    }
  };

  const ensureDomain = () => {
    const domain = operatorDomainRef.current || targetDomainNormalized;
    if (!domain) throw new Error("Enter a target domain");
    return domain;
  };

  const ensureTargetUrl = () => {
    if (targetUrl.trim()) return toUrl(targetUrl.trim());
    const domain = ensureDomain();
    return `https://${domain}`;
  };

  const fetchJson = async (url: string, options?: RequestInit) => {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  };

  const appendDiscoveredUrls = (urls: string[]) => {
    setDiscoveredUrls((prev) => {
      const map = new Map(prev.map((url) => [url, true]));
      urls.forEach((url) => map.set(url, true));
      return Array.from(map.keys());
    });
  };

  const ensureScrapeContent = async () => {
    const url = ensureTargetUrl();
    if (scrapeCache?.url === url && scrapeCache.content) return scrapeCache;
    const data = await fetchJson("/api/linklater/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const content = data.content || data.markdown || data.html || "";
    const cache = { url, content, title: data.title || data.metadata?.title };
    setScrapeCache(cache);
    return cache;
  };

  const handleWhois = () =>
    runAction("whois", "WHOIS", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/enrichment/whois", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain }),
      });
      const data = raw.data || raw;
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      if (data.registrant?.name) {
        items.push({
          id: `registrant-${data.registrant.name}`,
          title: data.registrant.name,
          subtitle: "Registrant",
          meta: {
            Organization: data.registrant.organization || "",
            Email: data.registrant.email || "",
          },
        });
        const entityNode = createNode("entity", data.registrant.name, "person");
        nodes.push(entityNode);
        edges.push(createEdge(rootId, entityNode.id, "registrant"));
      }

      if (Array.isArray(data.nameservers)) {
        data.nameservers.forEach((ns: string) => {
          const nsNode = createNode("nameserver", ns);
          nodes.push(nsNode);
          edges.push(createEdge(rootId, nsNode.id, "nameserver"));
        });
      }

      items.push({
        id: `whois-meta-${domain}`,
        title: "WHOIS Timeline",
        subtitle: data.registrar || "Registrar",
        meta: {
          Created: data.dates?.created || "",
          Updated: data.dates?.updated || "",
          Expires: data.dates?.expires || "",
        },
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `WHOIS record loaded for ${domain}`,
      };
    });

  const handleDns = () =>
    runAction("dns", "DNS", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/enrichment/dns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain }),
      });
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      (raw.a || raw.ip || []).forEach((ip: string) => {
        items.push({ id: `a-${ip}`, title: ip, subtitle: "A Record" });
        const ipNode = createNode("ip", ip);
        nodes.push(ipNode);
        edges.push(createEdge(rootId, ipNode.id, "resolves"));
      });

      (raw.ns || []).forEach((ns: string) => {
        items.push({ id: `ns-${ns}`, title: ns, subtitle: "Nameserver" });
        const nsNode = createNode("nameserver", ns);
        nodes.push(nsNode);
        edges.push(createEdge(rootId, nsNode.id, "nameserver"));
      });

      (raw.mx || []).forEach((mx: any) => {
        const label = mx.exchange || mx;
        items.push({ id: `mx-${label}`, title: label, subtitle: "Mail Server" });
        const mxNode = createNode("mail", label);
        nodes.push(mxNode);
        edges.push(createEdge(rootId, mxNode.id, "mx"));
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `DNS records loaded (${items.length} records)`,
      };
    });

  const handleSsl = () =>
    runAction("ssl", "SSL", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(`/api/linklater/subdomains/${encodeURIComponent(domain)}`);
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      (raw.results || []).forEach((entry: any) => {
        const subdomain = entry.subdomain || entry.domain || "";
        if (!subdomain) return;
        items.push({
          id: `cert-${subdomain}`,
          title: subdomain,
          subtitle: entry.issuer || "Certificate",
          meta: {
            NotBefore: entry.not_before || "",
            NotAfter: entry.not_after || "",
          },
        });
        const subNode = createNode("domain", subdomain, "subdomain");
        nodes.push(subNode);
        edges.push(createEdge(rootId, subNode.id, "subdomain"));
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Certificate transparency yielded ${items.length} subdomains`,
      };
    });

  const handleTech = () =>
    runAction("tech", "Tech Stack", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/extension/domain-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain }),
      });
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      (raw.technologies || []).forEach((tech: any) => {
        const name = tech.name || tech;
        items.push({ id: `tech-${name}`, title: name, subtitle: tech.category || "Technology" });
        const techNode = createNode("tech", name);
        nodes.push(techNode);
        edges.push(createEdge(rootId, techNode.id, "uses"));
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Detected ${items.length} technologies`,
      };
    });

  const handleGATrackers = () =>
    runAction("ga", "GA Trackers", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/linklater/ga/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain }),
      });
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      (raw.codes || []).forEach((code: any) => {
        const label = code.code || code;
        items.push({ id: `ga-${label}`, title: label, subtitle: code.type || "Tracker" });
        const trackerNode = createNode("tracker", label);
        nodes.push(trackerNode);
        edges.push(createEdge(rootId, trackerNode.id, "ga-code"));
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Found ${items.length} analytics codes`,
      };
    });

  const handleGARelated = () =>
    runAction("ga-related", "GA Related", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/linklater/ga/related", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, max_per_code: 20 }),
      });
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      const related = raw.related_by_code || {};
      Object.entries(related).forEach(([code, domains]) => {
        if (!Array.isArray(domains)) return;
        domains.forEach((relatedDomain: string) => {
          const label = toDomain(relatedDomain);
          if (!label) return;
          items.push({
            id: `ga-related-${code}-${label}`,
            title: label,
            subtitle: `Shared code ${code}`,
          });
          const node = createNode("domain", label);
          nodes.push(node);
          edges.push(createEdge(rootId, node.id, "shared-ga"));
        });
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Found ${items.length} related domains`,
      };
    });

  const handlePageScrape = () =>
    runAction("scrape", "Page Scrape", async () => {
      const url = ensureTargetUrl();
      const raw = await fetchJson("/api/linklater/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const content = raw.content || raw.markdown || raw.html || "";
      const metadata = extractMetadataFromHtml(content);
      setScrapeCache({ url, content, title: raw.title || metadata.title });
      const items: ResultItem[] = [
        {
          id: `scrape-${url}`,
          title: raw.title || metadata.title || url,
          subtitle: raw.source || "Scrape",
          url,
          meta: {
            Description: metadata.description || "",
            Language: metadata.language || "",
            Canonical: metadata.canonical || "",
          },
        },
      ];
      const rootId = makeId("domain", ensureDomain());
      const urlNode = createNode("url", url);
      const nodes = [urlNode];
      const edges = [createEdge(rootId, urlNode.id, "scrape")];

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Scraped ${url}`,
      };
    });

  const handleMetadata = () =>
    runAction("metadata", "Metadata", async () => {
      const scrape = await ensureScrapeContent();
      const metadata = extractMetadataFromHtml(scrape.content);
      const items: ResultItem[] = [
        {
          id: `meta-${scrape.url}`,
          title: metadata.title || scrape.title || scrape.url,
          subtitle: "Metadata Snapshot",
          meta: {
            Description: metadata.description || "",
            Canonical: metadata.canonical || "",
            Language: metadata.language || "",
          },
        },
      ];
      return {
        raw: metadata,
        items,
        summary: "Metadata extracted",
      };
    });

  const handleSchema = () =>
    runAction("schema", "Schema.org", async () => {
      const scrape = await ensureScrapeContent();
      const schema = extractJsonLd(scrape.content);
      const items: ResultItem[] = schema.map((entry, index) => ({
        id: `schema-${index}-${entry?.name || entry?.["@type"] || index}`,
        title: entry?.name || entry?.["@type"] || "Schema Item",
        subtitle: entry?.["@type"] || "Schema",
        meta: {
          Url: entry?.url || entry?.sameAs || "",
        },
      }));
      return {
        raw: schema,
        items,
        summary: `Parsed ${items.length} schema records`,
      };
    });

  const handleEntities = () =>
    runAction("entities", "Entity Extraction", async () => {
      const scrape = await ensureScrapeContent();
      const raw = await fetchJson("/api/linklater/extraction/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          html: scrape.content,
          url: scrape.url,
          extract_relationships: true,
        }),
      });
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", ensureDomain());

      [
        { list: raw.persons, type: "person" },
        { list: raw.companies, type: "company" },
        { list: raw.emails, type: "email" },
        { list: raw.phones, type: "phone" },
      ].forEach(({ list, type }) => {
        if (!Array.isArray(list)) return;
        list.forEach((entry: any) => {
          const value = entry.value || entry.name || entry.email || entry.phone;
          if (!value) return;
          items.push({ id: `${type}-${value}`, title: value, subtitle: type });
          const node = createNode("entity", value, type);
          nodes.push(node);
          edges.push(createEdge(rootId, node.id, "mentions"));
        });
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Extracted ${items.length} entities`,
      };
    });

  const handleArchiveKeywordSearch = () =>
    runAction("archive-keyword", "Archive Search", async () => {
      const domain = ensureDomain();
      const keywordValue = archiveKeyword.trim();
      if (!keywordValue) throw new Error("Enter a keyword for archive search");
      const { exactPhrases, variationPhrases, leftover } = parseArchiveKeywordInput(
        keywordValue,
        archiveKeywordMode
      );
      const targetUrl = ensureTargetUrl();
      const archiveQueries = [] as Array<{ keyword: string; expandKeywords: boolean }>;

      if (leftover) archiveQueries.push({ keyword: leftover, expandKeywords: true });
      exactPhrases.forEach((phrase) => archiveQueries.push({ keyword: phrase, expandKeywords: false }));

      const archiveResults: any[] = [];
      for (const query of archiveQueries) {
        const res = await fetchJson("/api/linklater/archives/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: targetUrl,
            keyword: query.keyword,
            quick: archiveQuick,
            maxSnapshots: archiveMaxSnapshots,
            expandKeywords: query.expandKeywords,
          }),
        });
        archiveResults.push(res);
      }

      let variationMatches: any[] = [];
      if (variationPhrases.length > 0) {
        const res = await fetchJson("/api/linklater/search-keyword-variations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            keywords: variationPhrases,
            verifySnippets: !archiveQuick,
            maxResultsPerSource: archiveMaxSnapshots,
          }),
        });
        variationMatches = Array.isArray(res.matches) ? res.matches : [];
      }

      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      archiveResults.forEach((result) => {
        if (result?.snapshot?.url) {
          const url = result.snapshot.url;
          items.push({
            id: `archive-${url}-${result.keyword}`,
            title: url,
            subtitle: `Keyword: ${result.keyword}`,
            url,
            meta: {
              Timestamp: result.snapshot.timestamp || "",
              Found: String(result.found),
            },
          });
          const node = createNode("url", url);
          nodes.push(node);
          edges.push(createEdge(rootId, node.id, "archive-hit"));
        }
      });

      variationMatches.forEach((match) => {
        if (!match?.url) return;
        const url = match.url;
        items.push({
          id: `variation-${url}-${match.variationMatched}`,
          title: url,
          subtitle: `Variation: ${match.variationMatched}`,
          url,
          meta: {
            Original: match.originalKeyword || "",
            Timestamp: match.timestamp || "",
          },
        });
        const node = createNode("url", url);
        nodes.push(node);
        edges.push(createEdge(rootId, node.id, "archive-variation"));
      });

      appendDiscoveredUrls(items.map((item) => item.url || "").filter(Boolean));

      return {
        raw: { archiveResults, variationMatches },
        items,
        nodes,
        edges,
        summary: `Archive hits: ${items.length}`,
      };
    });

  const handleArchiveChanges = () =>
    runAction("archive-changes", "Archive Changes", async () => {
      const url = ensureTargetUrl();
      const raw = await fetchJson("/api/linklater/archive/changes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          start_year: Number(archiveStartYear) || 2016,
          end_year: Number(archiveEndYear) || 2025,
        }),
      });
      const events = raw.change_events || raw.changes || [];
      const items: ResultItem[] = events.map((event: any, index: number) => ({
        id: `change-${index}-${event.timestamp || index}`,
        title: event.timestamp || "Snapshot",
        subtitle: event.change_type || event.event_type || "Change",
        meta: {
          Score: event.change_score || "",
          Url: event.url || url,
        },
      }));
      return {
        raw,
        items,
        summary: `Archive changes: ${items.length}`,
      };
    });

  const handleArchiveDiff = () =>
    runAction("archive-diff", "Archive Diff", async () => {
      const url = ensureTargetUrl();
      if (!archiveDiffA.trim() || !archiveDiffB.trim()) {
        throw new Error("Enter two archive timestamps");
      }
      const raw = await fetchJson("/api/linklater/archive/diff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          timestamp_a: archiveDiffA.trim(),
          timestamp_b: archiveDiffB.trim(),
        }),
      });

      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", ensureDomain());

      (raw.links_added || []).forEach((link: string) => {
        items.push({ id: `diff-add-${link}`, title: link, subtitle: "Link Added", url: link });
        const node = createNode("url", link);
        nodes.push(node);
        edges.push(createEdge(rootId, node.id, "archive-added"));
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Archive diff complete: ${items.length} additions`,
      };
    });

  const handleWayback = () =>
    runAction("wayback", "Wayback", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/alldom-actions/archive-versions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nodeId: domain }),
      });
      const versions = raw.versions || [];
      const items: ResultItem[] = versions.map((version: any, index: number) => ({
        id: `wayback-${version.timestamp || index}`,
        title: version.timestamp || version.date || "Snapshot",
        subtitle: version.url || "Wayback",
      }));
      return {
        raw,
        items,
        summary: `Wayback snapshots: ${items.length}`,
      };
    });

  const handleBacklinks = () =>
    runAction("backlinks-domains", "Backlinks", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(
        `/api/linklater/backlinks/${encodeURIComponent(domain)}?source=all&limit=${backlinkLimit}`
      );
      const results = raw.results || [];
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      results.forEach((result: any, index: number) => {
        const sourceDomain =
          result.source_domain ||
          (result.source_url ? extractDomainFromUrl(result.source_url) : "") ||
          result.domain ||
          result.url ||
          `source-${index}`;
        items.push({
          id: `backlink-${sourceDomain}-${index}`,
          title: sourceDomain,
          subtitle: result.source || "Backlink",
          meta: {
            Weight: result.weight || result.link_count || "",
          },
        });
        const sourceNode = createNode("domain", sourceDomain);
        nodes.push(sourceNode);
        edges.push(createEdge(sourceNode.id, rootId, "backlink"));
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Backlink domains: ${items.length}`,
      };
    });

  const handleBacklinksPages = () =>
    runAction("backlinks-pages", "Backlinks Pages", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/linklater/backlinks/pages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain,
          limit: Math.min(backlinkLimit, 200),
          top_domains: 20,
          include_anchor_text: true,
          include_majestic: true,
        }),
      });
      const pages = raw.pages || [];
      const items: ResultItem[] = pages.map((page: any, index: number) => ({
        id: `backlink-page-${index}-${page.source}`,
        title: page.source || page.source_url || "Backlink Page",
        subtitle: page.anchor_text || page.provider || "Anchor",
        url: page.source || page.source_url,
        meta: {
          TrustFlow: page.trust_flow || "",
          CitationFlow: page.citation_flow || "",
        },
      }));
      const nodes = pages
        .map((page: any) => page.source || page.source_url)
        .filter(Boolean)
        .map((url: string) => createNode("url", url));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(node.id, rootId, "backlink-page"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Backlink pages: ${items.length}`,
      };
    });

  const handleBacklinksHost = () =>
    runAction("backlinks-host", "Host Graph Backlinks", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/discovery/host-graph/backlinks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, limit: 200, include_subdomains: true }),
      });
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `host-${index}-${entry.domain || entry.url}`,
        title: entry.domain || entry.url || "Host",
        subtitle: entry.level || "host",
        meta: { Count: entry.link_count || 1 },
      }));
      const nodes = results
        .map((entry: any) => entry.domain || entry.url)
        .filter(Boolean)
        .map((domainValue: string) => createNode("domain", domainValue));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(node.id, rootId, "host-backlink"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Host graph backlinks: ${items.length}`,
      };
    });

  const handleBacklinksCC = () =>
    runAction("backlinks-cc", "CC Graph Backlinks", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/discovery/backlinks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, limit: 200, min_link_count: 1 }),
      });
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `cc-${index}-${entry.domain || entry.url}`,
        title: entry.domain || entry.url || "Domain",
        subtitle: "CC Graph",
        meta: { Count: entry.link_count || 1 },
      }));
      const nodes = results
        .map((entry: any) => entry.domain || entry.url)
        .filter(Boolean)
        .map((domainValue: string) => createNode("domain", domainValue));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(node.id, rootId, "cc-backlink"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `CC graph backlinks: ${items.length}`,
      };
    });

  const handleBacklinksGlobal = () =>
    runAction("backlinks-global", "GlobalLinks Backlinks", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/discovery/globallinks/backlinks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, limit: 100, archive: "CC-MAIN-2024-10", segments: "0" }),
      });
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `global-${index}-${entry.source_url}`,
        title: entry.source_url || "Source",
        subtitle: entry.anchor_text || "Anchor",
        url: entry.source_url,
        meta: { Provider: entry.provider || "globallinks" },
      }));
      const nodes = results
        .map((entry: any) => entry.source_url)
        .filter(Boolean)
        .map((url: string) => createNode("url", url));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(node.id, rootId, "globallinks"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `GlobalLinks results: ${items.length}`,
      };
    });

  const handleBacklinksMajestic = () =>
    runAction("backlinks-majestic", "Majestic Backlinks", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/eyed/backlinks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: domain, mode: "page", limit: 300 }),
      });
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `majestic-${index}-${entry.source_url || entry.url}`,
        title: entry.source_url || entry.url || "Backlink",
        subtitle: entry.anchor_text || entry.source_domain || "Majestic",
        url: entry.source_url || entry.url,
        meta: {
          TrustFlow: entry.trust_flow || "",
          CitationFlow: entry.citation_flow || "",
        },
      }));
      const nodes = results
        .map((entry: any) => entry.source_url || entry.url)
        .filter(Boolean)
        .map((url: string) => createNode("url", url));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(node.id, rootId, "majestic"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Majestic backlinks: ${items.length}`,
      };
    });

  const handleBacklinkArchives = () =>
    runAction("backlink-archives", "Backlink Archives", async () => {
      const domain = ensureDomain();
      const keywordValue = archiveKeyword.trim();
      if (!keywordValue) throw new Error("Enter a keyword to scan backlink archives");
      const raw = await fetchJson("/api/linklater/backlink-archives", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          targetDomain: domain,
          keyword: keywordValue,
          direction: "backlinks",
          maxDomains: 20,
          maxSnapshotsPerDomain: 10,
        }),
      });
      const results = raw.matches || raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `backlink-archive-${index}-${entry.url}`,
        title: entry.url || entry.domain || "Archive Hit",
        subtitle: entry.keyword || keywordValue,
        url: entry.url,
        meta: {
          Domain: entry.domain || "",
          Timestamp: entry.timestamp || "",
        },
      }));
      return {
        raw,
        items,
        summary: `Backlink archive hits: ${items.length}`,
      };
    });

  const handleBacklinkTemporal = () =>
    runAction("backlink-temporal", "Temporal Links", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/linklater/links/query-by-age", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_domain: domain,
          min_age_days: temporalMinAge ? Number(temporalMinAge) : undefined,
          max_age_days: temporalMaxAge ? Number(temporalMaxAge) : undefined,
          size: 100,
        }),
      });
      const links = raw.links || [];
      const items: ResultItem[] = links.map((link: any, index: number) => ({
        id: `temporal-${index}-${link.target_url || link.target_domain}`,
        title: link.target_domain || link.target_url || "Target",
        subtitle: link.first_seen || "Temporal",
        meta: {
          LastSeen: link.last_seen || "",
          Source: link.source_domain || "",
        },
      }));
      return {
        raw,
        items,
        summary: `Temporal link records: ${items.length}`,
      };
    });

  const handleOutlinks = () =>
    runAction("outlinks-domains", "Outlinks", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(
        `/api/linklater/outlinks/${encodeURIComponent(domain)}?source=all&limit=${outlinkLimit}`
      );
      const results = raw.results || [];
      const items: ResultItem[] = [];
      const nodes: GraphNode[] = [];
      const edges: GraphEdge[] = [];
      const rootId = makeId("domain", domain);

      results.forEach((result: any, index: number) => {
        const targetDomain =
          result.target_domain ||
          (result.target_url ? extractDomainFromUrl(result.target_url) : "") ||
          result.domain ||
          result.url ||
          `target-${index}`;
        items.push({
          id: `outlink-${targetDomain}-${index}`,
          title: targetDomain,
          subtitle: result.source || "Outlink",
          meta: {
            Weight: result.weight || result.link_count || "",
          },
        });
        const targetNode = createNode("domain", targetDomain);
        nodes.push(targetNode);
        edges.push(createEdge(rootId, targetNode.id, "outlink"));
      });

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Outlink domains: ${items.length}`,
      };
    });

  const handleOutlinksCC = () =>
    runAction("outlinks-cc", "CC Graph Outlinks", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/discovery/outlinks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, limit: 200, min_link_count: 1 }),
      });
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `cc-out-${index}-${entry.domain || entry.url}`,
        title: entry.domain || entry.url || "Target",
        subtitle: "CC Graph",
        meta: { Count: entry.link_count || 1 },
      }));
      const nodes = results
        .map((entry: any) => entry.domain || entry.url)
        .filter(Boolean)
        .map((domainValue: string) => createNode("domain", domainValue));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "cc-outlink"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `CC graph outlinks: ${items.length}`,
      };
    });

  const handleOutlinksExtract = () =>
    runAction("outlinks-extract", "Live Outlinks", async () => {
      const url = ensureTargetUrl();
      const raw = await fetchJson("/api/linklater/outlinks/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const links = raw.links || [];
      const items: ResultItem[] = links.map((link: string, index: number) => ({
        id: `extract-${index}-${link}`,
        title: link,
        subtitle: "Outlink",
        url: link,
      }));
      const nodes = links.map((link: string) => createNode("url", link));
      const rootId = makeId("domain", ensureDomain());
      const edges = nodes.map((node) => createEdge(rootId, node.id, "outlink"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Live outlinks: ${items.length}`,
      };
    });

  const handleLinkNeighbors = () =>
    runAction("link-neighbors", "Link Neighbors", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/discovery/similar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, limit: 100 }),
      });
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `neighbor-${index}-${entry.domain}`,
        title: entry.domain || "Related",
        subtitle: "Link Neighbor",
      }));
      const nodes = results
        .map((entry: any) => entry.domain)
        .filter(Boolean)
        .map((domainValue: string) => createNode("domain", domainValue));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "neighbor"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Link neighbors: ${items.length}`,
      };
    });

  const handleLinkHop = () =>
    runAction("link-hop", "Submarine", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/linklater/hop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain,
          direction: linkHopDirection,
          depth: linkHopDepth,
          maxPerHop: linkHopMax,
        }),
      });
      const nodes = (raw.nodes || []).map((node: any) => createNode("domain", node.domain || node.label));
      const edges = (raw.edges || []).map((edge: any, index: number) =>
        createEdge(
          makeId("domain", edge.source || edge.from || `n${index}`),
          makeId("domain", edge.target || edge.to || `m${index}`),
          edge.type || "hop"
        )
      );
      const items: ResultItem[] = nodes.map((node) => ({
        id: `hop-${node.label}`,
        title: node.label,
        subtitle: "Hop",
      }));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Hop nodes: ${items.length}`,
      };
    });

  const handleRelatedNameservers = () =>
    runAction("related-nameservers", "Nameserver Cluster", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/linklater/discovery/whois/cluster", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, include_nameserver: true, limit: 100 }),
      });
      const related = raw.related_domains || [];
      const items: ResultItem[] = related
        .filter((entry: any) => entry.match_type === "nameserver")
        .map((entry: any, index: number) => ({
          id: `ns-related-${index}-${entry.domain}`,
          title: entry.domain,
          subtitle: "Same nameserver",
          meta: { Nameserver: entry.nameserver || "" },
        }));
      const nodes = items.map((item) => createNode("domain", item.title));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "nameserver"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Nameserver cluster: ${items.length}`,
      };
    });

  const handleRelatedCohosted = () =>
    runAction("related-cohosted", "Co-hosted", async () => {
      const domain = ensureDomain();
      const dns = await fetchJson("/api/enrichment/dns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain }),
      });
      const raw = await fetchJson("/api/linklater/discovery/whois/cluster", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, include_nameserver: false, limit: 100 }),
      });
      const related = raw.related_domains || [];
      const items: ResultItem[] = related.map((entry: any, index: number) => ({
        id: `cohost-${index}-${entry.domain}`,
        title: entry.domain,
        subtitle: "Co-hosted",
        meta: { IP: dns?.ip || "" },
      }));
      const nodes = items.map((item) => createNode("domain", item.title));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "cohosted"));

      return {
        raw: { dns, cluster: raw },
        items,
        nodes,
        edges,
        summary: `Co-hosted domains: ${items.length}`,
      };
    });

  const handleRelatedMajestic = () =>
    runAction("related-majestic", "Majestic Related", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/eyed/backlinks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: domain, mode: "domain", limit: 200 }),
      });
      const results = raw.results || [];
      const unique = new Set<string>();
      results.forEach((entry: any) => {
        const sourceDomain = entry.source_domain || (entry.url ? extractDomainFromUrl(entry.url) : "");
        if (sourceDomain) unique.add(sourceDomain);
      });
      const items: ResultItem[] = Array.from(unique).map((value) => ({
        id: `majestic-related-${value}`,
        title: value,
        subtitle: "Majestic co-citation",
      }));
      const nodes = items.map((item) => createNode("domain", item.title));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "majestic-related"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Majestic related domains: ${items.length}`,
      };
    });

  const handleCCIndexDomain = () =>
    runAction("cc-index", "CC Index", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(
        `/api/linklater/cc-index/domain/${encodeURIComponent(domain)}?limit=500&allCollections=true`
      );
      const records = raw.records || [];
      const items: ResultItem[] = records.slice(0, 200).map((record: any, index: number) => ({
        id: `cc-${index}-${record.url}`,
        title: record.url,
        subtitle: record.mime || "CC Index",
        url: record.url,
      }));
      const nodes = items.map((item) => createNode("url", item.title));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "cc-index"));
      appendDiscoveredUrls(items.map((item) => item.title));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `CC index URLs: ${items.length}`,
      };
    });

  const handleCCFiletype = () =>
    runAction("cc-filetype", "CC Filetype", async () => {
      const domain = ensureDomain();
      const params = new URLSearchParams({
        filetype: filetypeQuery,
        limit: "500",
      });
      if (filetypeFromYear.trim()) params.set("fromYear", filetypeFromYear.trim());
      if (filetypeToYear.trim()) params.set("toYear", filetypeToYear.trim());
      const raw = await fetchJson(
        `/api/linklater/cc-index/filetype/${encodeURIComponent(domain)}?${params.toString()}`
      );
      const records = raw.records || [];
      const items: ResultItem[] = records.slice(0, 200).map((record: any, index: number) => ({
        id: `file-${index}-${record.url}`,
        title: record.url,
        subtitle: record.mime || record.filetype || "File",
        url: record.url,
      }));
      const nodes = items.map((item) => createNode("url", item.title));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "filetype"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Filetype results: ${items.length}`,
      };
    });

  const handleCCMimeStats = () =>
    runAction("cc-mime", "CC MIME", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(
        `/api/linklater/cc-index/mimes/${encodeURIComponent(domain)}?limit=${ccMimeLimit}`
      );
      const stats = raw.stats || raw.results || [];
      const items: ResultItem[] = (stats || []).map((stat: any, index: number) => ({
        id: `mime-${index}-${stat.mime}`,
        title: stat.mime || stat.type || "MIME",
        subtitle: "MIME",
        meta: { Count: stat.count || stat.total || "" },
      }));
      return {
        raw,
        items,
        summary: `MIME stats: ${items.length}`,
      };
    });

  const handleSearchEngines = () =>
    runAction("search-engines", "Search Engines", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(`/api/linklater/search-engines/${encodeURIComponent(domain)}`);
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `engine-${index}-${entry.url}`,
        title: entry.title || entry.url,
        subtitle: entry.source || "search",
        url: entry.url,
        meta: { Snippet: entry.snippet || "" },
      }));
      const nodes = results
        .map((entry: any) => entry.url)
        .filter(Boolean)
        .map((url: string) => createNode("url", url));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "search"));
      appendDiscoveredUrls(items.map((item) => item.url || "").filter(Boolean));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Search results: ${items.length}`,
      };
    });

  const handleSitemaps = () =>
    runAction("sitemaps", "Sitemaps", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(`/api/linklater/sitemaps/${encodeURIComponent(domain)}`);
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `sitemap-${index}-${entry.url}`,
        title: entry.url || entry,
        subtitle: "Sitemap",
        url: entry.url || entry,
      }));
      const nodes = items.map((item) => createNode("url", item.title));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "sitemap"));
      appendDiscoveredUrls(items.map((item) => item.title));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Sitemap URLs: ${items.length}`,
      };
    });

  const handleSubdomains = () =>
    runAction("subdomains", "Subdomains", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(`/api/linklater/subdomains/${encodeURIComponent(domain)}`);
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `subdomain-${index}-${entry.subdomain}`,
        title: entry.subdomain || entry.domain || "Subdomain",
        subtitle: "Subdomain",
      }));
      const nodes = items.map((item) => createNode("domain", item.title, "subdomain"));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "subdomain"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Subdomains: ${items.length}`,
      };
    });

  const handleMapDomain = () =>
    runAction("map-domain", "Map Domain", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(`/api/linklater/map/${encodeURIComponent(domain)}?limit=1000&includeSubdomains=true`);
      const urls = raw.urls || raw.results || [];
      const items: ResultItem[] = urls.slice(0, 200).map((url: string, index: number) => ({
        id: `map-${index}-${url}`,
        title: url,
        subtitle: "Map",
        url,
      }));
      const nodes = items.map((item) => createNode("url", item.title));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "map"));
      appendDiscoveredUrls(items.map((item) => item.title));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Mapped URLs: ${items.length}`,
      };
    });

  const handleNews = () =>
    runAction("news", "News", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/linklater/discovery/news", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: domain, max_results: 50 }),
      });
      const articles = raw.articles || [];
      const items: ResultItem[] = articles.map((article: any, index: number) => ({
        id: `news-${index}-${article.url}`,
        title: article.title || article.url,
        subtitle: article.source || "News",
        url: article.url,
        meta: { Published: article.publishedAt || "" },
      }));
      const nodes = items
        .map((item) => item.url)
        .filter(Boolean)
        .map((url) => createNode("url", url!));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "news"));
      return {
        raw,
        items,
        nodes,
        edges,
        summary: `News hits: ${items.length}`,
      };
    });

  const handleSocial = () =>
    runAction("social", "Social", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(`/api/linklater/search-engines/${encodeURIComponent(domain)}?social=true`);
      const results = raw.results || [];
      const filtered = results.filter((entry: any) =>
        /twitter.com|x.com|facebook.com|linkedin.com|reddit.com/i.test(entry.url || "")
      );
      const items: ResultItem[] = filtered.map((entry: any, index: number) => ({
        id: `social-${index}-${entry.url}`,
        title: entry.title || entry.url,
        subtitle: entry.source || "Social",
        url: entry.url,
      }));
      const nodes = items
        .map((item) => item.url)
        .filter(Boolean)
        .map((url) => createNode("url", url!));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "social"));
      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Social mentions: ${items.length}`,
      };
    });

  const handleBreach = () =>
    runAction("breach", "Breach", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/eyed/breaches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: domain, type: "domain" }),
      });
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `breach-${index}-${entry.email}`,
        title: entry.email || "Email",
        subtitle: entry.database_name || "Breach",
      }));
      const nodes = items
        .map((item) => item.title)
        .filter(Boolean)
        .map((email) => createNode("entity", email, "email"));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "breach"));
      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Breach records: ${items.length}`,
      };
    });

  const handleCorpusDomain = () =>
    runAction("corpus-domain", "Corpus Domain", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson(`/api/linklater/corpus/domain/${encodeURIComponent(domain)}?limit=${corpusLimit}`);
      const docs = raw.documents || raw.results || raw || [];
      const items: ResultItem[] = (docs || []).map((doc: any, index: number) => ({
        id: `corpus-${index}-${doc.url || doc.id}`,
        title: doc.title || doc.url || "Document",
        subtitle: doc.source || doc.domain || "Corpus",
        url: doc.url,
      }));
      const nodes = items
        .map((item) => item.url)
        .filter(Boolean)
        .map((url) => createNode("url", url!));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "corpus"));
      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Corpus docs: ${items.length}`,
      };
    });

  const handleCorpusSearch = () =>
    runAction("corpus-search", "Corpus Search", async () => {
      const domain = ensureDomain();
      if (!corpusQuery.trim()) throw new Error("Enter a corpus search keyword");
      const params = new URLSearchParams({
        query: corpusQuery.trim(),
        limit: corpusLimit.toString(),
        domain,
      });
      const raw = await fetchJson(`/api/linklater/corpus/search?${params.toString()}`);
      const results = raw.results || [];
      const items: ResultItem[] = results.map((entry: any, index: number) => ({
        id: `corpus-search-${index}-${entry.url}`,
        title: entry.title || entry.url || "Match",
        subtitle: entry.source || "Corpus",
        url: entry.url,
      }));
      const nodes = items
        .map((item) => item.url)
        .filter(Boolean)
        .map((url) => createNode("url", url!));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "corpus-match"));
      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Corpus matches: ${items.length}`,
      };
    });

  const handleLinkVelocity = () =>
    runAction("link-velocity", "Link Velocity", async () => {
      const domain = ensureDomain();
      const raw = await fetchJson("/api/linklater/links/velocity", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, period_days: linkVelocityDays }),
      });
      const items: ResultItem[] = [
        {
          id: `velocity-${domain}`,
          title: `Velocity: ${raw.status || raw.velocity || "n/a"}`,
          subtitle: `Period ${linkVelocityDays} days`,
          meta: {
            NewLinks: raw.new_links || raw.newLinks || "",
          },
        },
      ];
      return {
        raw,
        items,
        summary: "Velocity computed",
      };
    });

  const handleFullEnrich = () =>
    runAction("full-enrich", "Full Enrich", async () => {
      const domain = ensureDomain();
      const keywordValue = enrichKeyword.trim();
      const baseUrls = [ensureTargetUrl()];
      const extra = enrichUseDiscovered ? discoveredUrls.slice(0, enrichMaxUrls) : [];
      const urls = Array.from(new Set([...baseUrls, ...extra])).slice(0, enrichMaxUrls);
      if (urls.length === 0) throw new Error("No URLs available for enrich");
      const raw = await fetchJson("/api/linklater/enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          urls,
          keyword: keywordValue || undefined,
          options: {
            useArchiveScan: true,
            useCCGraph: true,
            useGlobalLinks: true,
            expandKeywords: true,
          },
        }),
      });
      const results = raw.results || {};
      const items: ResultItem[] = Object.keys(results).map((url) => ({
        id: `enrich-${url}`,
        title: url,
        subtitle: "Enriched",
        url,
      }));
      const nodes = items.map((item) => createNode("url", item.title));
      const rootId = makeId("domain", domain);
      const edges = nodes.map((node) => createEdge(rootId, node.id, "enrich"));

      return {
        raw,
        items,
        nodes,
        edges,
        summary: `Enriched ${items.length} URLs`,
      };
    });

  const handleEnrichAll = async () => {
    updateActionResult("enrich-all", { status: "loading", summary: "Running enrichment suite..." });
    const sequence = [
      { label: "WHOIS", run: handleWhois },
      { label: "DNS", run: handleDns },
      { label: "Tech Stack", run: handleTech },
      { label: "GA Trackers", run: handleGATrackers },
      { label: "GA Related", run: handleGARelated },
      { label: "Subdomains", run: handleSubdomains },
      { label: "Sitemaps", run: handleSitemaps },
      { label: "Search Engines", run: handleSearchEngines },
      { label: "CC Index", run: handleCCIndexDomain },
      { label: "Page Scrape", run: handlePageScrape },
      { label: "Metadata", run: handleMetadata },
      { label: "Schema.org", run: handleSchema },
      { label: "Entities", run: handleEntities },
      { label: "Archive Search", run: handleArchiveKeywordSearch },
      { label: "Archive Changes", run: handleArchiveChanges },
      { label: "Backlinks", run: handleBacklinks },
      { label: "Outlinks", run: handleOutlinks },
      { label: "Backlink Pages", run: handleBacklinksPages },
      { label: "Live Outlinks", run: handleOutlinksExtract },
      { label: "Nameservers", run: handleRelatedNameservers },
      { label: "Co-hosted", run: handleRelatedCohosted },
      { label: "Majestic Related", run: handleRelatedMajestic },
      { label: "News", run: handleNews },
      { label: "Breach", run: handleBreach },
      { label: "Full Enrich", run: handleFullEnrich },
    ];

    const completed: ResultItem[] = [];
    for (const action of sequence) {
      try {
        await action.run();
        completed.push({ id: `enrich-${action.label}`, title: action.label });
      } catch {
        continue;
      }
    }

    updateActionResult("enrich-all", {
      status: "success",
      items: completed,
      summary: `Enrich all complete: ${completed.length} actions`,
    });
  };

  const handleDiscoverAll = () => {
    const domain = targetDomainNormalized;
    if (!domain) {
      updateActionResult("discover-all", { status: "error", error: "Enter a target domain" });
      return;
    }

    if (discoverySourceRef.current) {
      discoverySourceRef.current.close();
    }

    setDiscovering(true);
    setDiscoveryLog([`Discovery started for ${domain}`]);
    updateActionResult("discover-all", { status: "loading", items: [] });

    const params = new URLSearchParams({
      firecrawlMap: "true",
      subdomains: "true",
      sitemaps: "true",
      searchEngines: "true",
    });
    const source = new EventSource(`/api/linklater/discover/${encodeURIComponent(domain)}?${params}`);
    discoverySourceRef.current = source;

    const items: ResultItem[] = [];
    const nodes: GraphNode[] = [];
    const edges: GraphEdge[] = [];
    const rootId = makeId("domain", domain);

    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "status") {
          setDiscoveryLog((prev) => [...prev, payload.message || "Status update"]);
        }
        if (payload.type === "url" && payload.data?.url) {
          const url = payload.data.url;
          items.push({
            id: `discover-${url}`,
            title: url,
            subtitle: payload.data.source || "discovery",
            url,
          });
          const node = createNode("url", url);
          nodes.push(node);
          edges.push(createEdge(rootId, node.id, "discover"));
          updateActionResult("discover-all", {
            status: "success",
            items: [...items],
            raw: payload,
            summary: `Discovered ${items.length} URLs`,
          });
          mergeGraph([node], [createEdge(rootId, node.id, "discover")]);
          appendDiscoveredUrls([url]);
        }
        if (payload.type === "complete") {
          source.close();
          setDiscovering(false);
        }
      } catch {
        return;
      }
    };

    source.onerror = () => {
      source.close();
      setDiscovering(false);
      updateActionResult("discover-all", {
        status: "error",
        error: "Discovery stream failed",
      });
    };
  };

  const handleStopDiscover = () => {
    discoverySourceRef.current?.close();
    setDiscovering(false);
    setDiscoveryLog((prev) => [...prev, "Discovery stopped"]);
  };

  const handleOperatorRun = async () => {
    setOperatorError(null);
    const parsed = parseLinklaterQuery(operatorQuery);
    if (!parsed) {
      setOperatorError("Operator syntax not recognized");
      return;
    }

    if (parsed.domain) {
      setTargetDomain(parsed.domain);
      operatorDomainRef.current = parsed.domain;
    }

    if (parsed.keyword) {
      setArchiveKeyword(parsed.keyword);
      const mode = parsed.keyword.includes("\"")
        ? "exact"
        : parsed.keyword.includes("'")
        ? "variation"
        : "semantic";
      setArchiveKeywordMode(mode);
    }

    const actionMap: Record<LinklaterAction, () => Promise<void> | void> = {
      discover: handleDiscoverAll,
      "page-scrape": handlePageScrape,
      "deep-crawl": handleMapDomain,
      "enrich-all": handleEnrichAll,
      "full-enrich": handleFullEnrich,
      "backlinks-domains": handleBacklinks,
      "backlinks-pages": handleBacklinksPages,
      "backlinks-host": handleBacklinksHost,
      "backlinks-cc": handleBacklinksCC,
      "backlinks-global": handleBacklinksGlobal,
      "backlinks-majestic": handleBacklinksMajestic,
      "backlink-archive": handleBacklinkArchives,
      "backlink-temporal": handleBacklinkTemporal,
      "outlinks-domains": handleOutlinks,
      "outlinks-pages": handleOutlinksExtract,
      "outlinks-cc": handleOutlinksCC,
      entities: handleEntities,
      filetype: handleCCFiletype,
      "archive-keyword": handleArchiveKeywordSearch,
      "archive-changes": handleArchiveChanges,
      "archive-diff": handleArchiveDiff,
      wayback: handleWayback,
      whois: handleWhois,
      ssl: handleSsl,
      dns: handleDns,
      subdomains: handleSubdomains,
      tech: handleTech,
      ga: handleGATrackers,
      "ga-related": handleGARelated,
      sitemap: handleSitemaps,
      "map-domain": handleMapDomain,
      "cc-index": handleCCIndexDomain,
      "search-engines": handleSearchEngines,
      metadata: handleMetadata,
      "cc-mime": handleCCMimeStats,
      schema: handleSchema,
      dehashed: handleBreach,
      "link-neighbors": handleLinkNeighbors,
      "link-hop": handleLinkHop,
      "related-nameservers": handleRelatedNameservers,
      "related-cohosted": handleRelatedCohosted,
      "related-majestic": handleRelatedMajestic,
      news: handleNews,
      social: handleSocial,
      breach: handleBreach,
      "link-velocity": handleLinkVelocity,
      "corpus-domain": handleCorpusDomain,
      "corpus-search": handleCorpusSearch,
    };

    const runner = actionMap[parsed.action];
    if (!runner) {
      setOperatorError(`Operator not wired: ${parsed.action}`);
      return;
    }

    try {
      await runner();
    } finally {
      operatorDomainRef.current = null;
    }
  };

  const handleUseSyntax = (syntax: string) => {
    setOperatorQuery(syntax);
    setOperatorError(null);
  };

  const graphNodesForView = graphView === "map" ? mapNodes : relationNodes;
  const graphEdgesForView = graphEdges.filter((edge) =>
    graphNodesForView.some((node) => node.id === edge.from || node.id === edge.to)
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="rounded-xl border border-slate-200 bg-white p-2 text-slate-700 shadow-sm">
                <Globe className="h-5 w-5" />
              </div>
              <div>
                <div className="text-lg font-semibold text-slate-900">Linklater Location</div>
                <div className="text-xs text-slate-500">Domain discovery + enrichment console</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className={`${BUTTON_BASE} ${viewMode === "formatted" ? BUTTON_PRIMARY : BUTTON_STANDARD}`}
                onClick={() => setViewMode("formatted")}
              >
                Formatted
              </button>
              <button
                type="button"
                className={`${BUTTON_BASE} ${viewMode === "raw" ? BUTTON_PRIMARY : BUTTON_STANDARD}`}
                onClick={() => setViewMode("raw")}
              >
                Raw
              </button>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <div className="mb-1 text-xs font-semibold text-slate-500">Target Domain</div>
                  <input
                    value={targetDomain}
                    onChange={(event) => setTargetDomain(event.target.value)}
                    placeholder="example.com"
                    className={INPUT_CLASS}
                  />
                </div>
                <div>
                  <div className="mb-1 text-xs font-semibold text-slate-500">Target URL (optional)</div>
                  <input
                    value={targetUrl}
                    onChange={(event) => setTargetUrl(event.target.value)}
                    placeholder={`https://${targetDomainNormalized || "example.com"}`}
                    className={INPUT_CLASS}
                  />
                </div>
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold text-slate-500">Unified Operator Bar</div>
                <div className="flex flex-wrap gap-2">
                  <input
                    data-universal-search="true"
                    value={operatorQuery}
                    onChange={(event) => setOperatorQuery(event.target.value)}
                    placeholder='archive:example.com "exact phrase"'
                    className={`${INPUT_CLASS} flex-1`}
                  />
                  <button
                    type="button"
                    className={`${BUTTON_BASE} ${BUTTON_PRIMARY}`}
                    onClick={handleOperatorRun}
                  >
                    <Search className="h-3.5 w-3.5" />
                    Run
                  </button>
                </div>
                {operatorError && <div className="mt-1 text-xs text-red-600">{operatorError}</div>}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className={`${BUTTON_BASE} ${section === "enrichment" ? BUTTON_PRIMARY : BUTTON_STANDARD}`}
                onClick={() => setSection("enrichment")}
              >
                Enrichment
              </button>
              <button
                type="button"
                className={`${BUTTON_BASE} ${section === "discovery" ? BUTTON_PRIMARY : BUTTON_STANDARD}`}
                onClick={() => setSection("discovery")}
              >
                Discovery
              </button>
              <button
                type="button"
                className={`${BUTTON_BASE} ${BUTTON_STANDARD}`}
                onClick={handleEnrichAll}
              >
                <Sparkles className="h-3.5 w-3.5" />
                Enrich All
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[1.3fr_0.7fr]">
        <div className="space-y-6">
          {section === "enrichment" ? (
            <>
              <SectionHeader
                title="Identity and Infrastructure"
                description="Ownership, infrastructure, and analytics fingerprints."
                icon={Shield}
              />
              <div className="grid gap-4 md:grid-cols-2">
                <ActionCard
                  title="WHOIS + Ownership"
                  description="Registrant identity, registrar, timeline."
                  icon={Shield}
                  tone="entity"
                  onRun={handleWhois}
                  syntax={`whois:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`whois:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["whois"]}
                />
                <ActionCard
                  title="DNS Records"
                  description="A, MX, NS, TXT extraction."
                  icon={Server}
                  onRun={handleDns}
                  syntax={`dns:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`dns:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["dns"]}
                />
                <ActionCard
                  title="SSL + Cert Transparency"
                  description="Subdomains and cert metadata."
                  icon={Shield}
                  onRun={handleSsl}
                  syntax={`ssl:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`ssl:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["ssl"]}
                />
                <ActionCard
                  title="Tech Stack"
                  description="Detected frameworks, trackers, stacks."
                  icon={Activity}
                  onRun={handleTech}
                  syntax={`tech:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`tech:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["tech"]}
                />
                <ActionCard
                  title="Analytics Codes"
                  description="GA/GTM trackers."
                  icon={BarChart3}
                  onRun={handleGATrackers}
                  syntax={`ga:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`ga:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["ga"]}
                />
                <ActionCard
                  title="GA Related Domains"
                  description="Sites sharing the same analytics codes."
                  icon={BarChart3}
                  onRun={handleGARelated}
                  syntax={`ga-related:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`ga-related:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["ga-related"]}
                />
              </div>

              <SectionHeader
                title="Content and Entities"
                description="Scrape, analyze, extract entities, and structured data."
                icon={FileText}
              />
              <div className="grid gap-4 md:grid-cols-2">
                <ActionCard
                  title="Page Scrape"
                  description="Live scrape with metadata capture."
                  icon={FileText}
                  onRun={handlePageScrape}
                  syntax={`!${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`!${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["scrape"]}
                />
                <ActionCard
                  title="Metadata Analysis"
                  description="Title, description, canonical, og tags."
                  icon={FileText}
                  onRun={handleMetadata}
                  syntax={`metadata:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`metadata:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["metadata"]}
                />
                <ActionCard
                  title="Schema.org Extraction"
                  description="JSON-LD extraction on the target page."
                  icon={Database}
                  tone="entity"
                  onRun={handleSchema}
                  syntax={`schema:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`schema:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["schema"]}
                />
                <ActionCard
                  title="Entity Extraction"
                  description="Companies, people, emails, phones."
                  icon={Users}
                  tone="entity"
                  onRun={handleEntities}
                  syntax={`extract:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`extract:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["entities"]}
                />
              </div>

              <SectionHeader
                title="Targeted Discovery"
                description="Map the target domain from multiple angles."
                icon={MapIcon}
              />
              <div className="grid gap-4 md:grid-cols-2">
                <ActionCard
                  title="Map Domain"
                  description="Firecrawl map of all pages."
                  icon={MapIcon}
                  onRun={handleMapDomain}
                  syntax={`map:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`map:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["map-domain"]}
                />
                <ActionCard
                  title="Sitemaps"
                  description="Robots and sitemap parsing."
                  icon={MapIcon}
                  onRun={handleSitemaps}
                  syntax={`sitemap:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`sitemap:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["sitemaps"]}
                />
                <ActionCard
                  title="Subdomains"
                  description="Certificate transparency + DNS."
                  icon={MapIcon}
                  onRun={handleSubdomains}
                  syntax={`subdomains:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`subdomains:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["subdomains"]}
                />
                <ActionCard
                  title="Search Engines"
                  description="Google, Bing, Brave discovery."
                  icon={Search}
                  onRun={handleSearchEngines}
                  syntax={`engines:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`engines:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["search-engines"]}
                />
                <ActionCard
                  title="CC Index Domain"
                  description="All CC-indexed URLs for the domain."
                  icon={Database}
                  onRun={handleCCIndexDomain}
                  syntax={`ccindex:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`ccindex:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["cc-index"]}
                />
              </div>

              <SectionHeader
                title="Archive Intelligence"
                description="Historical keyword scan, diffs, and timelines."
                icon={Archive}
              />
              <div className="grid gap-4 lg:grid-cols-2">
                <ActionCard
                  title="Archive Keyword Search"
                  description="Semantic, exact, and variation modes."
                  icon={Search}
                  onRun={handleArchiveKeywordSearch}
                  syntax={`archive:${targetDomainNormalized || "example.com"} ${formatArchiveOperatorKeyword(
                    archiveKeyword || "keyword",
                    archiveKeywordMode
                  )}`}
                  onUseSyntax={() =>
                    handleUseSyntax(
                      `archive:${targetDomainNormalized || "example.com"} ${formatArchiveOperatorKeyword(
                        archiveKeyword || "keyword",
                        archiveKeywordMode
                      )}`
                    )
                  }
                  viewMode={viewMode}
                  result={actionResults["archive-keyword"]}
                >
                  <div className="space-y-2">
                    <input
                      value={archiveKeyword}
                      onChange={(event) => setArchiveKeyword(event.target.value)}
                      placeholder='keyword or "exact phrase" or \'variation\''
                      className={INPUT_CLASS}
                    />
                    <div className="flex flex-wrap gap-2">
                      {(["semantic", "exact", "variation"] as const).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          className={`${BUTTON_BASE} ${
                            archiveKeywordMode === mode ? BUTTON_ENTITY : BUTTON_STANDARD
                          }`}
                          onClick={() => {
                            const nextValue = normalizeArchiveKeywordForMode(archiveKeyword, mode);
                            setArchiveKeyword(nextValue);
                            setArchiveKeywordMode(mode);
                          }}
                        >
                          {mode.toUpperCase()}
                        </button>
                      ))}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <label className="flex items-center gap-2 text-xs text-slate-500">
                        <input
                          type="checkbox"
                          checked={archiveQuick}
                          onChange={(event) => setArchiveQuick(event.target.checked)}
                        />
                        Quick scan
                      </label>
                      <input
                        type="number"
                        min={10}
                        value={archiveMaxSnapshots}
                        onChange={(event) => setArchiveMaxSnapshots(Number(event.target.value))}
                        className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                      />
                      <span className="text-xs text-slate-500">snapshots</span>
                    </div>
                  </div>
                </ActionCard>

                <div className="space-y-4">
                  <ActionCard
                    title="Archive Changes"
                    description="Digest-based change detection."
                    icon={Archive}
                    onRun={handleArchiveChanges}
                    syntax={`archive-changes:${targetDomainNormalized || "example.com"} ${archiveStartYear}-${archiveEndYear}`}
                    onUseSyntax={() =>
                      handleUseSyntax(
                        `archive-changes:${targetDomainNormalized || "example.com"} ${archiveStartYear}-${archiveEndYear}`
                      )
                    }
                    viewMode={viewMode}
                    result={actionResults["archive-changes"]}
                  >
                    <div className="flex gap-2">
                      <input
                        value={archiveStartYear}
                        onChange={(event) => setArchiveStartYear(event.target.value)}
                        placeholder="Start"
                        className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                      />
                      <input
                        value={archiveEndYear}
                        onChange={(event) => setArchiveEndYear(event.target.value)}
                        placeholder="End"
                        className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                      />
                    </div>
                  </ActionCard>
                  <ActionCard
                    title="Archive Diff"
                    description="Compare two snapshots."
                    icon={Archive}
                    onRun={handleArchiveDiff}
                    syntax={`archive-diff:${targetDomainNormalized || "example.com"} ${archiveDiffA || "YYYYMMDD"} ${
                      archiveDiffB || "YYYYMMDD"
                    }`}
                    onUseSyntax={() =>
                      handleUseSyntax(
                        `archive-diff:${targetDomainNormalized || "example.com"} ${archiveDiffA || "YYYYMMDD"} ${
                          archiveDiffB || "YYYYMMDD"
                        }`
                      )
                    }
                    viewMode={viewMode}
                    result={actionResults["archive-diff"]}
                  >
                    <div className="flex gap-2">
                      <input
                        value={archiveDiffA}
                        onChange={(event) => setArchiveDiffA(event.target.value)}
                        placeholder="Timestamp A"
                        className="w-full rounded-md border border-slate-200 px-2 py-1 text-xs"
                      />
                      <input
                        value={archiveDiffB}
                        onChange={(event) => setArchiveDiffB(event.target.value)}
                        placeholder="Timestamp B"
                        className="w-full rounded-md border border-slate-200 px-2 py-1 text-xs"
                      />
                    </div>
                  </ActionCard>
                  <ActionCard
                    title="Wayback Snapshots"
                    description="Historical capture list."
                    icon={Archive}
                    onRun={handleWayback}
                    syntax={`wayback:${targetDomainNormalized || "example.com"}`}
                    onUseSyntax={() => handleUseSyntax(`wayback:${targetDomainNormalized || "example.com"}`)}
                    viewMode={viewMode}
                    result={actionResults["wayback"]}
                  />
                </div>
              </div>

              <SectionHeader
                title="Link Graph"
                description="Backlinks, outlinks, and historical link intelligence."
                icon={Link2}
              />
              <div className="grid gap-4 md:grid-cols-2">
                <ActionCard
                  title="Backlink Domains"
                  description="Fast domain-level backlinks."
                  icon={Link2}
                  onRun={handleBacklinks}
                  syntax={`?bl !${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`?bl !${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["backlinks-domains"]}
                >
                  <input
                    type="number"
                    value={backlinkLimit}
                    onChange={(event) => setBacklinkLimit(Number(event.target.value))}
                    className="w-28 rounded-md border border-slate-200 px-2 py-1 text-xs"
                  />
                </ActionCard>
                <ActionCard
                  title="Backlink Pages"
                  description="Anchor text and enriched backlinks."
                  icon={Link2}
                  onRun={handleBacklinksPages}
                  syntax={`bl? !${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`bl? !${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["backlinks-pages"]}
                />
                <ActionCard
                  title="Host Graph Backlinks"
                  description="Host-level CC graph edges."
                  icon={Network}
                  onRun={handleBacklinksHost}
                  syntax={`backlinks-host:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`backlinks-host:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["backlinks-host"]}
                />
                <ActionCard
                  title="CC Graph Backlinks"
                  description="Common Crawl graph backlinks."
                  icon={Network}
                  onRun={handleBacklinksCC}
                  syntax={`backlinks-cc:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`backlinks-cc:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["backlinks-cc"]}
                />
                <ActionCard
                  title="GlobalLinks Backlinks"
                  description="Go binary WAT extraction."
                  icon={Link2}
                  onRun={handleBacklinksGlobal}
                  syntax={`globallinks:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`globallinks:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["backlinks-global"]}
                />
                <ActionCard
                  title="Majestic Backlinks"
                  description="Trust/Citation flow enrichment."
                  icon={Link2}
                  onRun={handleBacklinksMajestic}
                  syntax={`majestic-backlinks:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`majestic-backlinks:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["backlinks-majestic"]}
                />
                <ActionCard
                  title="Backlink Archive Scan"
                  description="Search keyword in referring domains."
                  icon={Archive}
                  onRun={handleBacklinkArchives}
                  syntax={`backlink-archive:${targetDomainNormalized || "example.com"} ${archiveKeyword || "keyword"}`}
                  onUseSyntax={() =>
                    handleUseSyntax(
                      `backlink-archive:${targetDomainNormalized || "example.com"} ${archiveKeyword || "keyword"}`
                    )
                  }
                  viewMode={viewMode}
                  result={actionResults["backlink-archives"]}
                />
                <ActionCard
                  title="Temporal Link Query"
                  description="Filter links by age window."
                  icon={Archive}
                  onRun={handleBacklinkTemporal}
                  syntax={`backlink-temporal:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`backlink-temporal:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["backlink-temporal"]}
                >
                  <div className="flex gap-2">
                    <input
                      value={temporalMinAge}
                      onChange={(event) => setTemporalMinAge(event.target.value)}
                      placeholder="Min days"
                      className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                    />
                    <input
                      value={temporalMaxAge}
                      onChange={(event) => setTemporalMaxAge(event.target.value)}
                      placeholder="Max days"
                      className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                    />
                  </div>
                </ActionCard>
                <ActionCard
                  title="Outlink Domains"
                  description="Domain-level outbound links."
                  icon={Link2}
                  onRun={handleOutlinks}
                  syntax={`?ol !${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`?ol !${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["outlinks-domains"]}
                >
                  <input
                    type="number"
                    value={outlinkLimit}
                    onChange={(event) => setOutlinkLimit(Number(event.target.value))}
                    className="w-28 rounded-md border border-slate-200 px-2 py-1 text-xs"
                  />
                </ActionCard>
                <ActionCard
                  title="CC Graph Outlinks"
                  description="Outbound links from CC graph."
                  icon={Network}
                  onRun={handleOutlinksCC}
                  syntax={`outlinks-cc:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`outlinks-cc:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["outlinks-cc"]}
                />
                <ActionCard
                  title="Live Outlink Extract"
                  description="Firecrawl outlink extraction."
                  icon={Link2}
                  onRun={handleOutlinksExtract}
                  syntax={`ol? !${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`ol? !${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["outlinks-extract"]}
                />
                <ActionCard
                  title="Link Neighbors"
                  description="Graph neighbors and co-link analysis."
                  icon={Network}
                  onRun={handleLinkNeighbors}
                  syntax={`link-neighbors:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`link-neighbors:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["link-neighbors"]}
                />
                <ActionCard
                  title="Submarine (Hop Links)"
                  description="Link hopping across backlink/outlink graph."
                  icon={Network}
                  onRun={handleLinkHop}
                  syntax={`link-hop:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`link-hop:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["link-hop"]}
                >
                  <div className="flex flex-wrap gap-2">
                    <select
                      value={linkHopDirection}
                      onChange={(event) => setLinkHopDirection(event.target.value as typeof linkHopDirection)}
                      className="rounded-md border border-slate-200 px-2 py-1 text-xs"
                    >
                      <option value="backlinks">backlinks</option>
                      <option value="outlinks">outlinks</option>
                      <option value="both">both</option>
                    </select>
                    <input
                      type="number"
                      value={linkHopDepth}
                      onChange={(event) => setLinkHopDepth(Number(event.target.value))}
                      className="w-20 rounded-md border border-slate-200 px-2 py-1 text-xs"
                    />
                    <input
                      type="number"
                      value={linkHopMax}
                      onChange={(event) => setLinkHopMax(Number(event.target.value))}
                      className="w-20 rounded-md border border-slate-200 px-2 py-1 text-xs"
                    />
                  </div>
                </ActionCard>
                <ActionCard
                  title="Link Velocity"
                  description="New links over time."
                  icon={BarChart3}
                  onRun={handleLinkVelocity}
                  syntax={`links-velocity:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`links-velocity:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["link-velocity"]}
                >
                  <input
                    type="number"
                    value={linkVelocityDays}
                    onChange={(event) => setLinkVelocityDays(Number(event.target.value))}
                    className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                  />
                </ActionCard>
              </div>

              <SectionHeader
                title="Related Domains"
                description="Nameserver clusters, co-hosted assets, co-citations."
                icon={Network}
              />
              <div className="grid gap-4 md:grid-cols-2">
                <ActionCard
                  title="Same Nameservers"
                  description="WHOIS cluster by nameserver."
                  icon={Network}
                  onRun={handleRelatedNameservers}
                  syntax={`nameservers:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`nameservers:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["related-nameservers"]}
                />
                <ActionCard
                  title="Co-hosted Domains"
                  description="Domains sharing the same IP."
                  icon={Network}
                  onRun={handleRelatedCohosted}
                  syntax={`cohosted:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`cohosted:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["related-cohosted"]}
                />
                <ActionCard
                  title="Majestic Related"
                  description="Co-citation and backlink overlap."
                  icon={Network}
                  onRun={handleRelatedMajestic}
                  syntax={`majestic-related:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`majestic-related:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["related-majestic"]}
                />
                <ActionCard
                  title="Breach Scan"
                  description="Leak records tied to the domain."
                  icon={Shield}
                  onRun={handleBreach}
                  syntax={`breach:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`breach:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["breach"]}
                />
              </div>

              <SectionHeader
                title="Corpus and File Discovery"
                description="Corpus indexing, filetype scans, MIME distribution."
                icon={Database}
              />
              <div className="grid gap-4 md:grid-cols-2">
                <ActionCard
                  title="CC Index Domain"
                  description="All CC-indexed URLs for the domain."
                  icon={Database}
                  onRun={handleCCIndexDomain}
                  syntax={`ccindex:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`ccindex:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["cc-index"]}
                />
                <ActionCard
                  title="CC Filetype Search"
                  description="Filter by filetype and year range."
                  icon={Database}
                  onRun={handleCCFiletype}
                  syntax={`${filetypeQuery.split(",")[0] || "file"}! :!${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() =>
                    handleUseSyntax(`${filetypeQuery.split(",")[0] || "file"}! :!${targetDomainNormalized || "example.com"}`)
                  }
                  viewMode={viewMode}
                  result={actionResults["cc-filetype"]}
                >
                  <div className="space-y-2">
                    <input
                      value={filetypeQuery}
                      onChange={(event) => setFiletypeQuery(event.target.value)}
                      className={INPUT_CLASS}
                      placeholder="pdf,docx,xlsx"
                    />
                    <div className="flex gap-2">
                      <input
                        value={filetypeFromYear}
                        onChange={(event) => setFiletypeFromYear(event.target.value)}
                        placeholder="From year"
                        className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                      />
                      <input
                        value={filetypeToYear}
                        onChange={(event) => setFiletypeToYear(event.target.value)}
                        placeholder="To year"
                        className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                      />
                    </div>
                  </div>
                </ActionCard>
                <ActionCard
                  title="CC MIME Stats"
                  description="Top MIME types on the domain."
                  icon={Database}
                  onRun={handleCCMimeStats}
                  syntax={`mime:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`mime:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["cc-mime"]}
                >
                  <input
                    type="number"
                    value={ccMimeLimit}
                    onChange={(event) => setCcMimeLimit(Number(event.target.value))}
                    className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                  />
                </ActionCard>
                <ActionCard
                  title="Corpus Domain"
                  description="Indexed corpus docs for this domain."
                  icon={Database}
                  onRun={handleCorpusDomain}
                  syntax={`corpus:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`corpus:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["corpus-domain"]}
                >
                  <input
                    type="number"
                    value={corpusLimit}
                    onChange={(event) => setCorpusLimit(Number(event.target.value))}
                    className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                  />
                </ActionCard>
                <ActionCard
                  title="Corpus Search"
                  description="Keyword search across indexed content."
                  icon={Database}
                  onRun={handleCorpusSearch}
                  syntax={`corpus:${targetDomainNormalized || "example.com"} ${corpusQuery || "keyword"}`}
                  onUseSyntax={() =>
                    handleUseSyntax(`corpus:${targetDomainNormalized || "example.com"} ${corpusQuery || "keyword"}`)
                  }
                  viewMode={viewMode}
                  result={actionResults["corpus-search"]}
                >
                  <input
                    value={corpusQuery}
                    onChange={(event) => setCorpusQuery(event.target.value)}
                    className={INPUT_CLASS}
                    placeholder="Search corpus"
                  />
                </ActionCard>
              </div>

              <SectionHeader
                title="News and Social"
                description="News coverage and social mentions."
                icon={Activity}
              />
              <div className="grid gap-4 md:grid-cols-2">
                <ActionCard
                  title="News Scan"
                  description="Recent articles and mentions."
                  icon={Activity}
                  onRun={handleNews}
                  syntax={`news:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`news:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["news"]}
                />
                <ActionCard
                  title="Social Mentions"
                  description="Social profile and post discovery."
                  icon={Activity}
                  onRun={handleSocial}
                  syntax={`social:${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`social:${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["social"]}
                />
              </div>

              <SectionHeader
                title="Full Enrichment Pipeline"
                description="Run the full enrichment stack and propagate to graph."
                icon={Sparkles}
              />
              <ActionCard
                title="Enrich All"
                description="Run every enrichment stage in sequence."
                icon={Sparkles}
                onRun={handleEnrichAll}
                runLabel="Run All"
                syntax={`enrich:${targetDomainNormalized || "example.com"}`}
                onUseSyntax={() => handleUseSyntax(`enrich:${targetDomainNormalized || "example.com"}`)}
                viewMode={viewMode}
                result={actionResults["enrich-all"]}
              />
              <ActionCard
                title="Full Enrich"
                description="Scrape, extract entities, links, archives."
                icon={Sparkles}
                onRun={handleFullEnrich}
                syntax={`full:${targetDomainNormalized || "example.com"} ${enrichKeyword || ""}`.trim()}
                onUseSyntax={() =>
                  handleUseSyntax(`full:${targetDomainNormalized || "example.com"} ${enrichKeyword || ""}`.trim())
                }
                viewMode={viewMode}
                result={actionResults["full-enrich"]}
              >
                <div className="space-y-2">
                  <input
                    value={enrichKeyword}
                    onChange={(event) => setEnrichKeyword(event.target.value)}
                    className={INPUT_CLASS}
                    placeholder="Optional keyword"
                  />
                  <label className="flex items-center gap-2 text-xs text-slate-500">
                    <input
                      type="checkbox"
                      checked={enrichUseDiscovered}
                      onChange={(event) => setEnrichUseDiscovered(event.target.checked)}
                    />
                    Include discovered URLs
                  </label>
                  <input
                    type="number"
                    value={enrichMaxUrls}
                    onChange={(event) => setEnrichMaxUrls(Number(event.target.value))}
                    className="w-24 rounded-md border border-slate-200 px-2 py-1 text-xs"
                  />
                </div>
              </ActionCard>
            </>
          ) : (
            <>
              <SectionHeader
                title="Discovery Controls"
                description="Find domains and URLs from every angle."
                icon={Search}
              />
              <div className="space-y-4">
                <ActionCard
                  title="Discover All"
                  description="Unified discovery sweep across map, sitemap, and search engines."
                  icon={RefreshCw}
                  onRun={handleDiscoverAll}
                  runLabel={discovering ? "Streaming" : "Discover"}
                  syntax={`?${targetDomainNormalized || "example.com"}`}
                  onUseSyntax={() => handleUseSyntax(`?${targetDomainNormalized || "example.com"}`)}
                  viewMode={viewMode}
                  result={actionResults["discover-all"]}
                >
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className={`${BUTTON_BASE} ${BUTTON_STANDARD}`}
                      onClick={handleStopDiscover}
                      disabled={!discovering}
                    >
                      Stop
                    </button>
                    <span className="text-xs text-slate-500">{discovering ? "Streaming" : "Idle"}</span>
                  </div>
                  {discoveryLog.length > 0 && (
                    <div className="max-h-40 overflow-auto rounded-lg border border-slate-100 bg-slate-50 p-2 text-xs text-slate-600">
                      {discoveryLog.map((log, index) => (
                        <div key={index}>{log}</div>
                      ))}
                    </div>
                  )}
                </ActionCard>
                <div className="grid gap-4 md:grid-cols-2">
                  <ActionCard
                    title="Map Domain"
                    description="Firecrawl map of all pages."
                    icon={MapIcon}
                    onRun={handleMapDomain}
                    syntax={`map:${targetDomainNormalized || "example.com"}`}
                    onUseSyntax={() => handleUseSyntax(`map:${targetDomainNormalized || "example.com"}`)}
                    viewMode={viewMode}
                    result={actionResults["map-domain"]}
                  />
                  <ActionCard
                    title="Sitemaps"
                    description="Robots and sitemap parsing."
                    icon={MapIcon}
                    onRun={handleSitemaps}
                    syntax={`sitemap:${targetDomainNormalized || "example.com"}`}
                    onUseSyntax={() => handleUseSyntax(`sitemap:${targetDomainNormalized || "example.com"}`)}
                    viewMode={viewMode}
                    result={actionResults["sitemaps"]}
                  />
                  <ActionCard
                    title="Subdomains"
                    description="Certificate transparency + DNS."
                    icon={MapIcon}
                    onRun={handleSubdomains}
                    syntax={`subdomains:${targetDomainNormalized || "example.com"}`}
                    onUseSyntax={() => handleUseSyntax(`subdomains:${targetDomainNormalized || "example.com"}`)}
                    viewMode={viewMode}
                    result={actionResults["subdomains"]}
                  />
                  <ActionCard
                    title="Search Engines"
                    description="Google, Bing, Brave discovery."
                    icon={Search}
                    onRun={handleSearchEngines}
                    syntax={`engines:${targetDomainNormalized || "example.com"}`}
                    onUseSyntax={() => handleUseSyntax(`engines:${targetDomainNormalized || "example.com"}`)}
                    viewMode={viewMode}
                    result={actionResults["search-engines"]}
                  />
                </div>
                <SectionHeader
                  title="Keyword Variations"
                  description="Find keyword variations via archive search."
                  icon={Search}
                />
                <ActionCard
                  title="Archive Keyword Variations"
                  description="Exact + semantic + variation scans."
                  icon={Search}
                  onRun={handleArchiveKeywordSearch}
                  syntax={`archive:${targetDomainNormalized || "example.com"} ${formatArchiveOperatorKeyword(
                    archiveKeyword || "keyword",
                    archiveKeywordMode
                  )}`}
                  onUseSyntax={() =>
                    handleUseSyntax(
                      `archive:${targetDomainNormalized || "example.com"} ${formatArchiveOperatorKeyword(
                        archiveKeyword || "keyword",
                        archiveKeywordMode
                      )}`
                    )
                  }
                  viewMode={viewMode}
                  result={actionResults["archive-keyword"]}
                >
                  <input
                    value={archiveKeyword}
                    onChange={(event) => setArchiveKeyword(event.target.value)}
                    className={INPUT_CLASS}
                    placeholder="keyword"
                  />
                </ActionCard>
              </div>
            </>
          )}
        </div>

        <aside className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold text-slate-900">Domain Graph Satellite</div>
              <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 text-xs">
                <button
                  type="button"
                  className={`rounded-md px-2 py-1 ${
                    graphView === "relations" ? "bg-slate-900 text-white" : "text-slate-500"
                  }`}
                  onClick={() => setGraphView("relations")}
                >
                  Relations
                </button>
                <button
                  type="button"
                  className={`rounded-md px-2 py-1 ${
                    graphView === "map" ? "bg-slate-900 text-white" : "text-slate-500"
                  }`}
                  onClick={() => setGraphView("map")}
                >
                  Map
                </button>
              </div>
            </div>
            <GraphSatellite centerLabel={targetDomainNormalized} nodes={graphNodesForView} edges={graphEdgesForView} />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="text-sm font-semibold text-slate-900">Profile Summary</div>
            <div className="mt-3 grid gap-2 text-xs text-slate-600">
              <div className="flex justify-between">
                <span>Domains</span>
                <span className="font-mono text-slate-700">{summaryStats.domains}</span>
              </div>
              <div className="flex justify-between">
                <span>URLs</span>
                <span className="font-mono text-blue-700">{summaryStats.urls}</span>
              </div>
              <div className="flex justify-between">
                <span>Entities</span>
                <span className="font-mono text-emerald-700">{summaryStats.entities}</span>
              </div>
              <div className="flex justify-between">
                <span>Trackers</span>
                <span className="font-mono text-amber-600">{summaryStats.trackers}</span>
              </div>
              <div className="flex justify-between">
                <span>Tech</span>
                <span className="font-mono text-indigo-700">{summaryStats.tech}</span>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="text-sm font-semibold text-slate-900">Entity Capsules</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {entityCapsules.length === 0 && <span className="text-xs text-slate-400">No entities yet.</span>}
              {entityCapsules.map((entity) => (
                <span key={entity} className={`${CHIP_BASE} ${ENTITY_CHIP}`}>
                  {entity}
                </span>
              ))}
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
};

export default LinklaterStandalone;
