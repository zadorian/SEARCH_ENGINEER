package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gocolly/colly/v2"
)

// CrawlConfig defines configuration for the crawler
type CrawlConfig struct {
	URLs             []string `json:"urls"`
	MaxConcurrent    int      `json:"max_concurrent"`
	RequestTimeout   int      `json:"request_timeout"`
	DelayMs          int      `json:"delay_ms"`
	UserAgent        string   `json:"user_agent"`
	CountryTLDs      []string `json:"country_tlds"`
	URLKeywords      []string `json:"url_keywords"`
	OutputFormat     string   `json:"output_format"`
	DetectJSRequired bool     `json:"detect_js_required"`
}

// OutlinkRecord represents an extracted outlink
type OutlinkRecord struct {
	URL        string `json:"url"`
	Domain     string `json:"domain"`
	AnchorText string `json:"anchor_text"`
	IsNoFollow bool   `json:"is_nofollow"`
	IsExternal bool   `json:"is_external"`
}

// CrawlResult represents the result of crawling a single URL
type CrawlResult struct {
	URL           string          `json:"url"`
	StatusCode    int             `json:"status_code"`
	ContentType   string          `json:"content_type"`
	Title         string          `json:"title"`
	Content       string          `json:"content"`
	HTML          string          `json:"html,omitempty"`
	Outlinks      []OutlinkRecord `json:"outlinks"`
	InternalLinks []string        `json:"internal_links"`
	NeedsJS       bool            `json:"needs_js"`
	Error         string          `json:"error,omitempty"`
	LatencyMs     int64           `json:"latency_ms"`
}

// CrawlStats tracks crawl statistics
type CrawlStats struct {
	Total       int64 `json:"total"`
	Success     int64 `json:"success"`
	Failed      int64 `json:"failed"`
	NeedsJS     int64 `json:"needs_js"`
	TotalTimeMs int64 `json:"total_time_ms"`
}

// SPA detection patterns
var spaIndicators = []string{
	`<div id="root"></div>`,
	`<div id="app"></div>`,
	`<div id="__next"></div>`,
	`<app-root></app-root>`,
	`__NEXT_DATA__`,
	`window.__INITIAL_STATE__`,
	`window.__NUXT__`,
	`window.__PRELOADED_STATE__`,
}

// Framework detection patterns
var frameworkPatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)react`),
	regexp.MustCompile(`(?i)vue\.?js`),
	regexp.MustCompile(`(?i)angular`),
	regexp.MustCompile(`(?i)ember`),
	regexp.MustCompile(`(?i)svelte`),
}

const (
	emptyBodyThreshold = 500 // chars
)

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	command := os.Args[1]

	switch command {
	case "crawl":
		handleCrawlCommand()
	case "test":
		handleTestCommand()
	case "--help", "-h":
		printUsage()
	default:
		fmt.Printf("Unknown command: %s\n", command)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println("JESTER Colly Crawler - High-Performance Static HTML Crawler")
	fmt.Println("============================================================")
	fmt.Println()
	fmt.Println("COMMANDS:")
	fmt.Println("  crawl     Crawl URLs from input file")
	fmt.Println("  test      Test crawl a single URL")
	fmt.Println()
	fmt.Println("CRAWL USAGE:")
	fmt.Println("  ./colly_crawler crawl --urls=urls.json --output=results.json [OPTIONS]")
	fmt.Println()
	fmt.Println("  --urls=FILE            JSON file with URL list (or - for stdin)")
	fmt.Println("  --output=FILE          Output file (or - for stdout)")
	fmt.Println("  --concurrent=NUM       Max concurrent requests (default: 500)")
	fmt.Println("  --timeout=SEC          Request timeout in seconds (default: 30)")
	fmt.Println("  --delay=MS             Delay between requests in ms (default: 0)")
	fmt.Println("  --user-agent=UA        Custom user agent")
	fmt.Println("  --country-tlds=TLDS    Filter outlinks to these TLDs (.uk,.fr)")
	fmt.Println("  --url-keywords=KW      Filter outlinks containing keywords")
	fmt.Println("  --format=FMT           Output format: json, ndjson (default: ndjson)")
	fmt.Println("  --detect-js            Detect pages needing JS rendering (default: true)")
	fmt.Println("  --include-html         Include raw HTML in output")
	fmt.Println()
	fmt.Println("TEST USAGE:")
	fmt.Println("  ./colly_crawler test <URL>")
	fmt.Println()
	fmt.Println("EXAMPLES:")
	fmt.Println("  # Crawl 1000 URLs with high concurrency")
	fmt.Println("  ./colly_crawler crawl --urls=urls.json --concurrent=500 --output=results.ndjson")
	fmt.Println()
	fmt.Println("  # Test single URL")
	fmt.Println("  ./colly_crawler test https://example.com")
	fmt.Println()
	fmt.Println("  # Pipe URLs and output")
	fmt.Println("  cat urls.txt | ./colly_crawler crawl --urls=- --output=-")
}

func handleCrawlCommand() {
	config := parseCrawlArgs()

	// Load URLs
	urls, err := loadURLs(config.URLs)
	if err != nil {
		log.Fatalf("Failed to load URLs: %v", err)
	}

	if len(urls) == 0 {
		log.Fatal("No URLs to crawl")
	}

	fmt.Fprintf(os.Stderr, "🚀 Starting JESTER Colly Crawler\n")
	fmt.Fprintf(os.Stderr, "📊 URLs to crawl: %d\n", len(urls))
	fmt.Fprintf(os.Stderr, "⚡ Max concurrent: %d\n", config.MaxConcurrent)
	fmt.Fprintf(os.Stderr, "⏱️  Timeout: %ds\n", config.RequestTimeout)
	fmt.Fprintf(os.Stderr, "\n")

	// Setup output
	outputFile := getArgValue("--output")
	var output io.Writer
	if outputFile == "" || outputFile == "-" {
		output = os.Stdout
	} else {
		f, err := os.Create(outputFile)
		if err != nil {
			log.Fatalf("Failed to create output file: %v", err)
		}
		defer f.Close()
		output = f
	}

	// Run crawler
	stats := crawlURLs(urls, config, output)

	// Print stats
	fmt.Fprintf(os.Stderr, "\n✅ Crawl completed!\n")
	fmt.Fprintf(os.Stderr, "📊 Total: %d | Success: %d | Failed: %d | NeedsJS: %d\n",
		stats.Total, stats.Success, stats.Failed, stats.NeedsJS)
	fmt.Fprintf(os.Stderr, "⏱️  Total time: %dms (%.1f pages/sec)\n",
		stats.TotalTimeMs, float64(stats.Total)/float64(stats.TotalTimeMs)*1000)
}

func handleTestCommand() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: ./colly_crawler test <URL>")
		os.Exit(1)
	}

	testURL := os.Args[2]
	fmt.Printf("🔍 Testing URL: %s\n\n", testURL)

	config := CrawlConfig{
		MaxConcurrent:    1,
		RequestTimeout:   30,
		DetectJSRequired: true,
	}

	result := crawlSingleURL(testURL, config, true)

	// Pretty print result
	resultJSON, _ := json.MarshalIndent(result, "", "  ")
	fmt.Println(string(resultJSON))
}

func parseCrawlArgs() CrawlConfig {
	config := CrawlConfig{
		MaxConcurrent:    500,
		RequestTimeout:   30,
		DelayMs:          0,
		UserAgent:        "Mozilla/5.0 (compatible; JESTER/1.5; +https://drill-search.com/bot)",
		OutputFormat:     "ndjson",
		DetectJSRequired: true,
	}

	// Parse URL file
	if urlFile := getArgValue("--urls"); urlFile != "" {
		config.URLs = []string{urlFile}
	}

	// Parse concurrent
	if c := getArgValue("--concurrent"); c != "" {
		if val, err := strconv.Atoi(c); err == nil {
			config.MaxConcurrent = val
		}
	}

	// Parse timeout
	if t := getArgValue("--timeout"); t != "" {
		if val, err := strconv.Atoi(t); err == nil {
			config.RequestTimeout = val
		}
	}

	// Parse delay
	if d := getArgValue("--delay"); d != "" {
		if val, err := strconv.Atoi(d); err == nil {
			config.DelayMs = val
		}
	}

	// Parse user agent
	if ua := getArgValue("--user-agent"); ua != "" {
		config.UserAgent = ua
	}

	// Parse country TLDs
	if tlds := getArgValue("--country-tlds"); tlds != "" {
		config.CountryTLDs = strings.Split(tlds, ",")
	}

	// Parse URL keywords
	if kw := getArgValue("--url-keywords"); kw != "" {
		config.URLKeywords = strings.Split(kw, ",")
	}

	// Parse format
	if fmt := getArgValue("--format"); fmt != "" {
		config.OutputFormat = fmt
	}

	// Parse detect-js
	if hasArg("--no-detect-js") {
		config.DetectJSRequired = false
	}

	return config
}

func loadURLs(sources []string) ([]string, error) {
	var urls []string

	for _, source := range sources {
		var reader io.Reader

		if source == "-" {
			reader = os.Stdin
		} else {
			f, err := os.Open(source)
			if err != nil {
				return nil, err
			}
			defer f.Close()
			reader = f
		}

		// Try JSON first
		var jsonURLs []string
		decoder := json.NewDecoder(reader)
		if err := decoder.Decode(&jsonURLs); err != nil {
			// Fall back to line-by-line
			if source != "-" {
				f, _ := os.Open(source)
				defer f.Close()
				reader = f
			}

			scanner := bufio.NewScanner(reader)
			for scanner.Scan() {
				line := strings.TrimSpace(scanner.Text())
				if line != "" && !strings.HasPrefix(line, "#") {
					urls = append(urls, line)
				}
			}
		} else {
			urls = append(urls, jsonURLs...)
		}
	}

	return urls, nil
}

func crawlURLs(urls []string, config CrawlConfig, output io.Writer) CrawlStats {
	var stats CrawlStats
	stats.Total = int64(len(urls))

	startTime := time.Now()

	// Create collector
	c := colly.NewCollector(
		colly.Async(true),
		colly.UserAgent(config.UserAgent),
	)

	// Set limits
	c.Limit(&colly.LimitRule{
		DomainGlob:  "*",
		Parallelism: config.MaxConcurrent,
		Delay:       time.Duration(config.DelayMs) * time.Millisecond,
	})

	// Set timeout
	c.SetRequestTimeout(time.Duration(config.RequestTimeout) * time.Second)

	// Results channel for ordered output
	results := make(chan CrawlResult, 1000)
	var wg sync.WaitGroup
	var writerWg sync.WaitGroup // Wait for writer goroutine to finish
	var writeMutex sync.Mutex
	includeHTML := hasArg("--include-html")

	// Writer goroutine
	writerWg.Add(1)
	go func() {
		defer writerWg.Done()
		isFirst := true
		if config.OutputFormat == "json" {
			output.Write([]byte("[\n"))
		}

		for result := range results {
			writeMutex.Lock()
			var resultBytes []byte
			var err error

			if config.OutputFormat == "json" {
				if !isFirst {
					output.Write([]byte(",\n"))
				}
				resultBytes, err = json.MarshalIndent(result, "  ", "  ")
			} else {
				resultBytes, err = json.Marshal(result)
			}

			if err == nil {
				output.Write(resultBytes)
				if config.OutputFormat == "ndjson" {
					output.Write([]byte("\n"))
				}
			}
			isFirst = false
			writeMutex.Unlock()
		}

		if config.OutputFormat == "json" {
			output.Write([]byte("\n]"))
		}
	}()

	// Track URL start times
	startTimes := make(map[string]time.Time)
	var startTimeMutex sync.Mutex

	// OnRequest - record start time
	c.OnRequest(func(r *colly.Request) {
		startTimeMutex.Lock()
		startTimes[r.URL.String()] = time.Now()
		startTimeMutex.Unlock()
	})

	// OnResponse - process successful responses
	c.OnResponse(func(r *colly.Response) {
		startTimeMutex.Lock()
		startTime := startTimes[r.Request.URL.String()]
		delete(startTimes, r.Request.URL.String())
		startTimeMutex.Unlock()

		latency := time.Since(startTime).Milliseconds()

		result := processResponse(r, config, includeHTML)
		result.LatencyMs = latency

		if result.NeedsJS {
			atomic.AddInt64(&stats.NeedsJS, 1)
		}
		atomic.AddInt64(&stats.Success, 1)

		results <- result
		wg.Done()
	})

	// OnError - handle failures
	c.OnError(func(r *colly.Response, err error) {
		startTimeMutex.Lock()
		startTime := startTimes[r.Request.URL.String()]
		delete(startTimes, r.Request.URL.String())
		startTimeMutex.Unlock()

		latency := time.Since(startTime).Milliseconds()

		result := CrawlResult{
			URL:        r.Request.URL.String(),
			StatusCode: r.StatusCode,
			Error:      err.Error(),
			LatencyMs:  latency,
		}

		atomic.AddInt64(&stats.Failed, 1)

		results <- result
		wg.Done()
	})

	// Queue all URLs
	for _, u := range urls {
		wg.Add(1)
		c.Visit(u)
	}

	// Wait for all requests to complete
	c.Wait()
	wg.Wait()
	close(results)

	// Wait for writer goroutine to finish writing all results
	writerWg.Wait()

	stats.TotalTimeMs = time.Since(startTime).Milliseconds()

	return stats
}

func crawlSingleURL(targetURL string, config CrawlConfig, includeHTML bool) CrawlResult {
	var result CrawlResult
	result.URL = targetURL

	startTime := time.Now()

	c := colly.NewCollector(
		colly.UserAgent(config.UserAgent),
	)

	c.SetRequestTimeout(time.Duration(config.RequestTimeout) * time.Second)

	c.OnResponse(func(r *colly.Response) {
		result = processResponse(r, config, includeHTML)
	})

	c.OnError(func(r *colly.Response, err error) {
		result = CrawlResult{
			URL:        targetURL,
			StatusCode: r.StatusCode,
			Error:      err.Error(),
		}
	})

	c.Visit(targetURL)

	result.LatencyMs = time.Since(startTime).Milliseconds()

	return result
}

func processResponse(r *colly.Response, config CrawlConfig, includeHTML bool) CrawlResult {
	result := CrawlResult{
		URL:         r.Request.URL.String(),
		StatusCode:  r.StatusCode,
		ContentType: r.Headers.Get("Content-Type"),
	}

	html := string(r.Body)

	// Extract title
	titleRegex := regexp.MustCompile(`<title[^>]*>([^<]+)</title>`)
	if matches := titleRegex.FindStringSubmatch(html); len(matches) > 1 {
		result.Title = strings.TrimSpace(matches[1])
	}

	// Extract text content (simplified - removes HTML tags)
	textContent := extractTextContent(html)
	if len(textContent) > 10000 {
		textContent = textContent[:10000] // Limit content size
	}
	result.Content = textContent

	// Include HTML if requested
	if includeHTML {
		result.HTML = html
	}

	// Extract links
	baseURL := r.Request.URL
	outlinks, internalLinks := extractLinks(html, baseURL, config)
	result.Outlinks = outlinks
	result.InternalLinks = internalLinks

	// Detect if JS rendering is needed
	if config.DetectJSRequired {
		result.NeedsJS = needsJSRendering(html, textContent)
	}

	return result
}

func extractTextContent(html string) string {
	// Remove script and style tags
	scriptRegex := regexp.MustCompile(`(?is)<script[^>]*>.*?</script>`)
	html = scriptRegex.ReplaceAllString(html, "")

	styleRegex := regexp.MustCompile(`(?is)<style[^>]*>.*?</style>`)
	html = styleRegex.ReplaceAllString(html, "")

	// Remove all HTML tags
	tagRegex := regexp.MustCompile(`<[^>]+>`)
	text := tagRegex.ReplaceAllString(html, " ")

	// Normalize whitespace
	spaceRegex := regexp.MustCompile(`\s+`)
	text = spaceRegex.ReplaceAllString(text, " ")

	return strings.TrimSpace(text)
}

func extractLinks(html string, baseURL *url.URL, config CrawlConfig) ([]OutlinkRecord, []string) {
	var outlinks []OutlinkRecord
	var internalLinks []string

	// Link extraction regex - captures ALL links, not just text anchors
	// Uses non-greedy match for the full <a>...</a> block to handle nested tags like <img>
	linkRegex := regexp.MustCompile(`(?is)<a\s+[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>`)
	nofollowRegex := regexp.MustCompile(`rel=["'][^"']*nofollow[^"']*["']`)
	// Regex to extract plain text from anchor content (strips HTML tags)
	tagStripRegex := regexp.MustCompile(`<[^>]+>`)

	matches := linkRegex.FindAllStringSubmatch(html, -1)

	for _, match := range matches {
		if len(match) < 3 {
			continue
		}

		href := match[1]
		// Extract anchor text by stripping any nested HTML tags
		anchorHTML := match[2]
		anchor := strings.TrimSpace(tagStripRegex.ReplaceAllString(anchorHTML, " "))
		anchor = strings.Join(strings.Fields(anchor), " ") // Normalize whitespace
		fullTag := match[0]

		// Parse URL
		linkURL, err := url.Parse(href)
		if err != nil {
			continue
		}

		// Resolve relative URLs
		if !linkURL.IsAbs() {
			linkURL = baseURL.ResolveReference(linkURL)
		}

		// Skip non-http(s) links
		if linkURL.Scheme != "http" && linkURL.Scheme != "https" {
			continue
		}

		// Check if external
		isExternal := linkURL.Host != baseURL.Host

		// Check nofollow
		isNoFollow := nofollowRegex.MatchString(fullTag)

		if isExternal {
			// Apply filters
			if !shouldIncludeOutlink(linkURL, config) {
				continue
			}

			outlinks = append(outlinks, OutlinkRecord{
				URL:        linkURL.String(),
				Domain:     linkURL.Host,
				AnchorText: anchor,
				IsNoFollow: isNoFollow,
				IsExternal: true,
			})
		} else {
			internalLinks = append(internalLinks, linkURL.String())
		}
	}

	return outlinks, internalLinks
}

func shouldIncludeOutlink(linkURL *url.URL, config CrawlConfig) bool {
	// Check country TLD filter
	if len(config.CountryTLDs) > 0 {
		matched := false
		for _, tld := range config.CountryTLDs {
			if strings.HasSuffix(linkURL.Host, tld) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	// Check URL keyword filter
	if len(config.URLKeywords) > 0 {
		matched := false
		urlStr := strings.ToLower(linkURL.String())
		for _, keyword := range config.URLKeywords {
			if strings.Contains(urlStr, strings.ToLower(keyword)) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	return true
}

func needsJSRendering(html, textContent string) bool {
	// Check for SPA indicators
	for _, indicator := range spaIndicators {
		if strings.Contains(html, indicator) {
			return true
		}
	}

	// Check for framework patterns in script sources
	for _, pattern := range frameworkPatterns {
		if pattern.MatchString(html) {
			// Additional check - is there actual content?
			if len(textContent) < emptyBodyThreshold {
				return true
			}
		}
	}

	// Check for empty body
	bodyRegex := regexp.MustCompile(`(?is)<body[^>]*>(.*?)</body>`)
	if matches := bodyRegex.FindStringSubmatch(html); len(matches) > 1 {
		bodyHTML := matches[1]
		bodyText := extractTextContent(bodyHTML)
		if len(bodyText) < emptyBodyThreshold {
			return true
		}
	}

	// Check for noscript warning
	if strings.Contains(html, "<noscript>") {
		noscriptRegex := regexp.MustCompile(`(?is)<noscript[^>]*>(.*?)</noscript>`)
		if matches := noscriptRegex.FindStringSubmatch(html); len(matches) > 1 {
			noscriptContent := strings.ToLower(matches[1])
			if strings.Contains(noscriptContent, "javascript") ||
				strings.Contains(noscriptContent, "enable") ||
				strings.Contains(noscriptContent, "browser") {
				return true
			}
		}
	}

	return false
}

// Helper functions
func getArgValue(arg string) string {
	for _, a := range os.Args {
		if strings.HasPrefix(a, arg+"=") {
			return strings.TrimPrefix(a, arg+"=")
		}
	}
	return ""
}

func hasArg(arg string) bool {
	for _, a := range os.Args {
		if a == arg {
			return true
		}
	}
	return false
}
