package main

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	CC_INDEX_BASE = "https://index.commoncrawl.org"
	CC_DATA_BASE  = "https://data.commoncrawl.org"
	DEFAULT_ARCHIVE = "CC-MAIN-2024-51"
)

// CCIndexRecord from Common Crawl Index API
type CCIndexRecord struct {
	URL       string `json:"url"`
	URLKey    string `json:"urlkey"`
	Timestamp string `json:"timestamp"`
	Digest    string `json:"digest"`
	Length    string `json:"length"`
	Offset    string `json:"offset"`
	Filename  string `json:"filename"`
	Status    string `json:"status"`
	Mime      string `json:"mime"`
}

// ContentResult represents fetched content
type ContentResult struct {
	Domain        string `json:"domain"`
	URL           string `json:"url"`
	Content       string `json:"content"`
	ContentLength int    `json:"content_length"`
	Status        int    `json:"status"`
	LatencyMs     int64  `json:"latency_ms"`
	Source        string `json:"source"`
	WARCPath      string `json:"warc_path,omitempty"`
	Error         string `json:"error,omitempty"`
}

// Stats for progress tracking
type Stats struct {
	Total     int64
	Success   int64
	Failed    int64
	IndexHits int64
}

var stats Stats

func main() {
	log.SetOutput(os.Stderr)

	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	command := os.Args[1]

	switch command {
	case "fetch":
		handleFetchCommand()
	case "index":
		handleIndexCommand()
	case "batch":
		handleBatchCommand()
	case "--help", "-h":
		printUsage()
	default:
		fmt.Printf("Unknown command: %s\n", command)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println("CCWARC - Common Crawl Content Fetcher")
	fmt.Println("=====================================")
	fmt.Println()
	fmt.Println("COMMANDS:")
	fmt.Println("  fetch    Fetch content for domains from CC WARC files")
	fmt.Println("  index    Query CC Index for domain locations (without fetching)")
	fmt.Println("  batch    Process domains from file with CC Index + WARC fetch")
	fmt.Println()
	fmt.Println("FETCH USAGE (with pre-computed index records):")
	fmt.Println("  ./ccwarc fetch --records=index_records.ndjson --threads=50")
	fmt.Println()
	fmt.Println("INDEX USAGE (lookup only):")
	fmt.Println("  ./ccwarc index --domains=domain1.com,domain2.com --archive=CC-MAIN-2024-51")
	fmt.Println()
	fmt.Println("BATCH USAGE (full pipeline: index lookup + WARC fetch):")
	fmt.Println("  ./ccwarc batch --input=domains.txt --archive=CC-MAIN-2024-51 --threads=50")
	fmt.Println()
	fmt.Println("OPTIONS:")
	fmt.Println("  --domains=DOMAINS      Comma-separated domains")
	fmt.Println("  --input=FILE           Input file with domains (one per line)")
	fmt.Println("  --records=FILE         Pre-computed CC Index records (NDJSON)")
	fmt.Println("  --archive=ARCHIVE      CC archive (default: CC-MAIN-2024-51)")
	fmt.Println("  --threads=NUM          Concurrent fetches (default: 50)")
	fmt.Println("  --output=FILE          Output file (default: stdout)")
	fmt.Println("  --timeout=SECS         Request timeout (default: 30)")
}

func handleFetchCommand() {
	recordsFile := getArgValue("--records")
	if recordsFile == "" {
		log.Fatal("Error: --records parameter is required")
	}

	threads := getIntArg("--threads", 50)
	outputFile := getArgValue("--output")
	timeout := getIntArg("--timeout", 30)

	log.Printf("Loading CC Index records from: %s\n", recordsFile)

	// Load records
	records, err := loadIndexRecords(recordsFile)
	if err != nil {
		log.Fatalf("Failed to load records: %v", err)
	}

	log.Printf("Loaded %d records, fetching with %d threads...\n", len(records), threads)

	// Fetch content
	results := fetchWARCContent(records, threads, timeout)

	// Output
	writeResults(results, outputFile)

	log.Printf("Done. Success: %d, Failed: %d\n", stats.Success, stats.Failed)
}

func handleIndexCommand() {
	domainsStr := getArgValue("--domains")
	inputFile := getArgValue("--input")
	archive := getArgValue("--archive")
	if archive == "" {
		archive = DEFAULT_ARCHIVE
	}

	var domains []string

	if domainsStr != "" {
		domains = strings.Split(domainsStr, ",")
	} else if inputFile != "" {
		var err error
		domains, err = loadDomainsFromFile(inputFile)
		if err != nil {
			log.Fatalf("Failed to load domains: %v", err)
		}
	} else {
		log.Fatal("Error: --domains or --input parameter is required")
	}

	threads := getIntArg("--threads", 20)
	outputFile := getArgValue("--output")

	log.Printf("Querying CC Index for %d domains (archive: %s)\n", len(domains), archive)

	// Query CC Index
	records := queryIndexBatch(domains, archive, threads)

	log.Printf("Found %d index records\n", len(records))

	// Output as NDJSON
	var out *os.File
	if outputFile == "" || outputFile == "-" {
		out = os.Stdout
	} else {
		var err error
		out, err = os.Create(outputFile)
		if err != nil {
			log.Fatalf("Failed to create output file: %v", err)
		}
		defer out.Close()
	}

	for _, rec := range records {
		jsonBytes, _ := json.Marshal(rec)
		out.Write(jsonBytes)
		out.WriteString("\n")
	}
}

func handleBatchCommand() {
	inputFile := getArgValue("--input")
	if inputFile == "" {
		log.Fatal("Error: --input parameter is required")
	}

	archive := getArgValue("--archive")
	if archive == "" {
		archive = DEFAULT_ARCHIVE
	}

	threads := getIntArg("--threads", 50)
	outputFile := getArgValue("--output")
	timeout := getIntArg("--timeout", 30)

	// Load domains
	domains, err := loadDomainsFromFile(inputFile)
	if err != nil {
		log.Fatalf("Failed to load domains: %v", err)
	}

	stats.Total = int64(len(domains))
	log.Printf("Processing %d domains (archive: %s, threads: %d)\n", len(domains), archive, threads)

	// Phase 1: Query CC Index
	log.Println("Phase 1: Querying CC Index...")
	indexStart := time.Now()
	records := queryIndexBatch(domains, archive, threads/2) // Use half threads for index
	log.Printf("  Found %d index records in %v\n", len(records), time.Since(indexStart))

	// Phase 2: Fetch WARC content
	log.Println("Phase 2: Fetching WARC content...")
	fetchStart := time.Now()
	results := fetchWARCContent(records, threads, timeout)
	log.Printf("  Fetched %d results in %v\n", len(results), time.Since(fetchStart))

	// Output
	writeResults(results, outputFile)

	log.Printf("Done. Total: %d, CC Index hits: %d, Content fetched: %d, Failed: %d\n",
		stats.Total, stats.IndexHits, stats.Success, stats.Failed)
}

func loadDomainsFromFile(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var domains []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		domain := strings.TrimSpace(scanner.Text())
		if domain != "" && !strings.HasPrefix(domain, "#") {
			domains = append(domains, domain)
		}
	}
	return domains, scanner.Err()
}

func loadIndexRecords(path string) ([]CCIndexRecord, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var records []CCIndexRecord
	scanner := bufio.NewScanner(file)
	// Increase buffer for large lines
	buf := make([]byte, 1024*1024)
	scanner.Buffer(buf, 1024*1024)

	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			continue
		}
		var rec CCIndexRecord
		if err := json.Unmarshal([]byte(line), &rec); err == nil {
			records = append(records, rec)
		}
	}
	return records, scanner.Err()
}

func queryIndexBatch(domains []string, archive string, threads int) []CCIndexRecord {
	var results []CCIndexRecord
	var mutex sync.Mutex
	var wg sync.WaitGroup
	guard := make(chan struct{}, threads)

	client := &http.Client{Timeout: 15 * time.Second}

	for _, domain := range domains {
		wg.Add(1)
		guard <- struct{}{}

		go func(d string) {
			defer wg.Done()
			defer func() { <-guard }()

			records := queryIndex(client, d, archive)
			if len(records) > 0 {
				atomic.AddInt64(&stats.IndexHits, 1)
				mutex.Lock()
				// Take best record (first one, usually most recent)
				results = append(results, records[0])
				mutex.Unlock()
			}
		}(domain)
	}

	wg.Wait()
	return results
}

func queryIndex(client *http.Client, domain, archive string) []CCIndexRecord {
	// Query for domain/* to get all pages
	url := fmt.Sprintf("%s/%s-index?url=%s/*&output=json&fl=url,timestamp,digest,length,offset,filename,status,mime&limit=1",
		CC_INDEX_BASE, archive, domain)

	resp, err := client.Get(url)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return nil
	}

	var records []CCIndexRecord
	scanner := bufio.NewScanner(resp.Body)
	for scanner.Scan() {
		var rec CCIndexRecord
		if err := json.Unmarshal(scanner.Bytes(), &rec); err == nil {
			// Add domain for convenience
			rec.URLKey = domain
			records = append(records, rec)
		}
	}

	return records
}

func fetchWARCContent(records []CCIndexRecord, threads, timeout int) []ContentResult {
	var results []ContentResult
	var mutex sync.Mutex
	var wg sync.WaitGroup
	guard := make(chan struct{}, threads)

	client := &http.Client{Timeout: time.Duration(timeout) * time.Second}

	for _, rec := range records {
		wg.Add(1)
		guard <- struct{}{}

		go func(r CCIndexRecord) {
			defer wg.Done()
			defer func() { <-guard }()

			result := fetchWARC(client, r)
			mutex.Lock()
			results = append(results, result)
			if result.Error == "" && result.ContentLength > 0 {
				atomic.AddInt64(&stats.Success, 1)
			} else {
				atomic.AddInt64(&stats.Failed, 1)
			}
			mutex.Unlock()
		}(rec)
	}

	wg.Wait()
	return results
}

func fetchWARC(client *http.Client, rec CCIndexRecord) ContentResult {
	start := time.Now()

	// Parse offset and length
	offset, _ := strconv.ParseInt(rec.Offset, 10, 64)
	length, _ := strconv.ParseInt(rec.Length, 10, 64)

	if rec.Filename == "" || length == 0 {
		return ContentResult{
			Domain: rec.URLKey,
			URL:    rec.URL,
			Error:  "missing_warc_info",
			Source: "cc_failed",
		}
	}

	// Range request to CC
	warcURL := fmt.Sprintf("%s/%s", CC_DATA_BASE, rec.Filename)
	req, _ := http.NewRequest("GET", warcURL, nil)
	req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", offset, offset+length-1))

	resp, err := client.Do(req)
	if err != nil {
		return ContentResult{
			Domain:    rec.URLKey,
			URL:       rec.URL,
			Error:     err.Error(),
			Source:    "cc_failed",
			LatencyMs: time.Since(start).Milliseconds(),
		}
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 && resp.StatusCode != 206 {
		return ContentResult{
			Domain:    rec.URLKey,
			URL:       rec.URL,
			Status:    resp.StatusCode,
			Error:     fmt.Sprintf("http_%d", resp.StatusCode),
			Source:    "cc_failed",
			LatencyMs: time.Since(start).Milliseconds(),
		}
	}

	// Read compressed data
	compressed, err := io.ReadAll(resp.Body)
	if err != nil {
		return ContentResult{
			Domain:    rec.URLKey,
			URL:       rec.URL,
			Error:     "read_error",
			Source:    "cc_failed",
			LatencyMs: time.Since(start).Milliseconds(),
		}
	}

	// Decompress
	content := extractHTMLFromWARC(compressed)
	if content == "" {
		return ContentResult{
			Domain:    rec.URLKey,
			URL:       rec.URL,
			Error:     "decompress_failed",
			Source:    "cc_failed",
			LatencyMs: time.Since(start).Milliseconds(),
		}
	}

	status, _ := strconv.Atoi(rec.Status)

	return ContentResult{
		Domain:        rec.URLKey,
		URL:           rec.URL,
		Content:       content,
		ContentLength: len(content),
		Status:        status,
		LatencyMs:     time.Since(start).Milliseconds(),
		Source:        "cc",
		WARCPath:      rec.Filename,
	}
}

func extractHTMLFromWARC(compressed []byte) string {
	// Try gzip decompression
	reader, err := gzip.NewReader(strings.NewReader(string(compressed)))
	var data []byte
	if err == nil {
		data, err = io.ReadAll(reader)
		reader.Close()
		if err != nil {
			// Fall back to raw data
			data = compressed
		}
	} else {
		// Not gzipped, use raw
		data = compressed
	}

	text := string(data)

	// WARC format: WARC headers, blank line, HTTP headers, blank line, body
	// Find the double CRLF separating sections
	parts := strings.SplitN(text, "\r\n\r\n", 3)

	var body string
	if len(parts) >= 3 {
		// parts[0] = WARC headers, parts[1] = HTTP headers, parts[2] = body
		body = parts[2]
	} else if len(parts) == 2 {
		body = parts[1]
	} else {
		body = text
	}

	// Basic validation - should look like HTML
	if strings.Contains(body, "<") && strings.Contains(body, ">") {
		return body
	}

	return ""
}

func writeResults(results []ContentResult, outputFile string) {
	var out *os.File
	if outputFile == "" || outputFile == "-" {
		out = os.Stdout
	} else {
		var err error
		out, err = os.Create(outputFile)
		if err != nil {
			log.Fatalf("Failed to create output file: %v", err)
		}
		defer out.Close()
	}

	for _, result := range results {
		jsonBytes, _ := json.Marshal(result)
		out.Write(jsonBytes)
		out.WriteString("\n")
	}
}

// Helper functions for argument parsing
func getArgValue(arg string) string {
	for _, a := range os.Args {
		if strings.HasPrefix(a, arg+"=") {
			return strings.TrimPrefix(a, arg+"=")
		}
	}
	return ""
}

func getIntArg(arg string, defaultVal int) int {
	if val := getArgValue(arg); val != "" {
		if intVal, err := strconv.Atoi(val); err == nil {
			return intVal
		}
	}
	return defaultVal
}
