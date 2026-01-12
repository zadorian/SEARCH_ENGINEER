import cors from "cors";
import express, { Request, Response } from "express";
import { Readable } from "stream";
import linkLaterRouter, { streamLinkLaterSearch } from "../../../server/routers/linkLaterRouter";
import entityProfilesRouter from "../../../server/routers/entityProfilesRouter";
import extensionRouter from "../../../server/routers/extensionRouter";
import alldomActionsRouter from "../../../server/routers/alldomActionsRouter";
import eyedRouter from "../../../server/routers/eyedRouter";
import whoisExpressRouter from "../../../server/routers/whoisExpressRouter";
import scrapeRouter from "../../../server/routers/scrapeRouter";
import { getPythonBackendBaseUrl } from "../../../server/utils/pythonApiBase";

const app = express();
const PORT = process.env.PORT || 3002;
const PYTHON_BACKEND_URL = getPythonBackendBaseUrl();

app.use(cors());
app.use(express.json({ limit: "10mb" }));

app.get("/health", (_req, res) => {
  res.json({ status: "ok", pythonBase: PYTHON_BACKEND_URL });
});

// SSE stream from Linklater engine
app.get("/api/search/stream/linklater", streamLinkLaterSearch);

// Primary Linklater endpoints (Node-powered)
app.use("/api/linklater", linkLaterRouter);

// Supporting enrichment endpoints used by the standalone UI
app.use(entityProfilesRouter);
app.use(extensionRouter);
app.use("/api/alldom-actions", alldomActionsRouter);
app.use("/api/eyed", eyedRouter);
app.use(whoisExpressRouter);
app.use(scrapeRouter);

const proxyToPython = async (req: Request, res: Response) => {
  try {
    const targetUrl = `${PYTHON_BACKEND_URL}${req.originalUrl}`;
    const headers: Record<string, string> = {};

    Object.entries(req.headers).forEach(([key, value]) => {
      if (!value || key.toLowerCase() === "host") return;
      headers[key] = Array.isArray(value) ? value.join(",") : String(value);
    });

    const hasBody = !["GET", "HEAD"].includes(req.method.toUpperCase());
    const body = hasBody ? JSON.stringify(req.body ?? {}) : undefined;

    if (hasBody && !headers["content-type"]) {
      headers["content-type"] = "application/json";
    }

    const response = await fetch(targetUrl, {
      method: req.method,
      headers,
      body,
    });

    res.status(response.status);
    response.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (lower === "content-encoding") return;
      if (lower === "transfer-encoding") return;
      res.setHeader(key, value);
    });

    if (!response.body) {
      const text = await response.text();
      res.send(text);
      return;
    }

    Readable.fromWeb(response.body as unknown as ReadableStream).pipe(res);
  } catch (error) {
    console.error("[Linklater Standalone] Proxy failed:", error);
    res.status(500).json({ error: "Proxy failed", detail: (error as Error).message });
  }
};

// Catch-all proxy for Linklater Python routes not covered by the Node router
app.all("/api/linklater/*", proxyToPython);
app.all("/api/discovery/*", proxyToPython);

app.listen(PORT, () => {
  console.log(`[Linklater Standalone] Server running at http://localhost:${PORT}`);
});
