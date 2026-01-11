package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/kris-dev-hub/globallinks/pkg/commoncrawl"
	"github.com/kris-dev-hub/globallinks/pkg/fileutils"
)

const (
	healthCheckMode = false // disable health check for cclinks
	sleepBetweenWat = 5     // reduced sleep for faster processing
)

// OutlinkFilter defines filtering criteria for outlinks
type OutlinkFilter struct {
	TargetDomains    []string          // Specific domains to extract outlinks from
	CountryTLDs      []string          // Country TLDs to include (e.g., .uk, .fr, .de)
	URLKeywords      []string          // Keywords that must be in the outlink URL
	ExcludeKeywords  []string          // Keywords to exclude from outlink URLs
	MinAnchorLength  int               // Minimum anchor text length
	MaxResults       int               // Maximum results per domain
	OutputFormat     string            // Output format: json, csv, txt
	IncludeInternal  bool              // Include internal links
	CustomFilters    map[string]string // Custom regex filters
}

// OutlinkResult represents an extracted outlink with metadata
type OutlinkResult struct {
	SourceDomain    string `json:"source_domain"`
	SourceURL       string `json:"source_url"`
	TargetDomain    string `json:"target_domain"`
	TargetURL       string `json:"target_url"`
	AnchorText      string `json:"anchor_text"`
	LinkContext     string `json:"link_context,omitempty"`
	DateDiscovered  string `json:"date_discovered"`
	SourceIP        string `json:"source_ip,omitempty"`
	IsNoFollow      bool   `json:"is_nofollow"`
	MatchedFilter   string `json:"matched_filter,omitempty"`
	RelevanceScore  int    `json:"relevance_score,omitempty"`
}

func main() {
	// Set log output to stderr to avoid polluting stdout data
	log.SetOutput(os.Stderr)

	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	command := os.Args[1]
	
	switch command {
	case "extract":
		handleExtractCommand()
	case "backlinks":
		handleBacklinksCommand()
	case "sniper":
		handleSniperCommand()
	case "filter":
		handleFilterCommand()
	case "search":
		handleSearchCommand()
	case "--help", "-h":
		printUsage()
	default:
		fmt.Printf("Unknown command: %s\n", command)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println("CCLinks - Common Crawl Link Tool")
	fmt.Println("=================================")
	fmt.Println()
	fmt.Println("COMMANDS:")
	fmt.Println("  extract    Extract outlinks FROM specific domains")
	fmt.Println("  backlinks  Find backlinks pointing TO a target domain (Trawler)")
	fmt.Println("  sniper     Find backlinks from known sources (Sniper)")
	fmt.Println("  filter     Filter existing link data")
	fmt.Println("  search     Search for links matching criteria")
	fmt.Println()
	fmt.Println("EXTRACT USAGE:")
	fmt.Println("  ./cclinks extract --domains=\"domain1.com,domain2.com\" --archive=CC-MAIN-2021-04 [OPTIONS]")
	fmt.Println()
	fmt.Println("BACKLINKS USAGE:")
	fmt.Println("  ./cclinks backlinks --target-domain=\"example.com\" --archive=CC-MAIN-2021-04 [OPTIONS]")
	fmt.Println()
	fmt.Println("SNIPER USAGE:")
	fmt.Println("  ./cclinks sniper --target-domain=\"example.com\" --source-domains=\"src1.com,src2.com\" --archive=CC-MAIN-2024-10 [OPTIONS]")
	fmt.Println()
	fmt.Println("EXTRACT OPTIONS:")
	fmt.Println("  --domains=DOMAINS        Comma-separated list of source domains to extract from")
	fmt.Println("  --archive=ARCHIVE        Common Crawl archive name (e.g., CC-MAIN-2021-04)")
	fmt.Println("  --segments=SEGMENTS      Segments to process (e.g., 0-5 or 1,3,5)")
	fmt.Println("  --country-tlds=TLDS      Include only outlinks to these country TLDs (.uk,.fr,.de)")
	fmt.Println("  --url-keywords=KEYWORDS  Include only outlinks containing these keywords")
	fmt.Println("  --exclude=KEYWORDS       Exclude outlinks containing these keywords")
	fmt.Println("  --min-anchor=LENGTH      Minimum anchor text length (default: 3)")
	fmt.Println("  --max-results=NUM        Maximum results per domain (default: 1000)")
	fmt.Println("  --format=FORMAT          Output format: json, csv, txt (default: json)")
	fmt.Println("  --include-internal       Include internal links")
	fmt.Println("  --threads=NUM            Number of processing threads (default: 2)")
	fmt.Println("  --output=FILE            Output file path")
	fmt.Println()
	fmt.Println("BACKLINKS OPTIONS:")
	fmt.Println("  --target-domain=DOMAIN   Domain to find backlinks for")
	fmt.Println("  --archive=ARCHIVE        Common Crawl archive name")
	fmt.Println("  --source-tlds=TLDS       Include only backlinks from these TLDs")
	fmt.Println("  --source-keywords=KEYS   Include only backlinks from pages with these keywords")
	fmt.Println()
	fmt.Println("FILTER USAGE:")
	fmt.Println("  ./cclinks filter --input=data.json --country-tlds=.uk,.fr")
	fmt.Println()
	fmt.Println("SEARCH USAGE:")
	fmt.Println("  ./cclinks search --target-domain=bbc.com --input=data/links/")
	fmt.Println()
	fmt.Println("EXAMPLES:")
	fmt.Println("  # Extract outlinks FROM BBC to UK domains")
	fmt.Println("  ./cclinks extract --domains=\"bbc.com\" --country-tlds=\".uk\" --archive=CC-MAIN-2024-10")
	fmt.Println()
	fmt.Println("  # Find who links TO example.com from government sites")
	fmt.Println("  ./cclinks backlinks --target-domain=\"example.com\" --source-tlds=\".gov,.edu\" --archive=CC-MAIN-2024-10")
	fmt.Println()
	fmt.Println("  # Extract outlinks containing 'news' or 'article'")
	fmt.Println("  ./cclinks extract --domains=\"guardian.com,independent.co.uk\" --url-keywords=\"news,article\"")
}

func handleExtractCommand() {
	// Parse command line arguments
	filter := parseExtractArgs()
	
	if len(filter.TargetDomains) == 0 {
		log.Println("Error: --domains parameter is required")
		os.Exit(1)
	}
	
	archive := getArgValue("--archive")
	if archive == "" {
		log.Println("Error: --archive parameter is required")
		os.Exit(1)
	}
	
	if !commoncrawl.IsCorrectArchiveFormat(archive) {
		log.Println("Error: Invalid archive format")
		os.Exit(1)
	}
	
	segments := getArgValue("--segments")
	if segments == "" {
		segments = "0" // Default to first segment
	}
	
	threads := getIntArg("--threads", 2)
	outputFile := getArgValue("--output")
	if outputFile == "" {
		outputFile = fmt.Sprintf("outlinks_%s_%d.%s", archive, time.Now().Unix(), filter.OutputFormat)
	}
	
	log.Printf("🔗 Starting outlink extraction...\n")
	log.Printf("📁 Archive: %s\n", archive)
	log.Printf("🎯 Target domains: %v\n", filter.TargetDomains)
	log.Printf("🌍 Country TLDs: %v\n", filter.CountryTLDs)
	log.Printf("🔍 URL keywords: %v\n", filter.URLKeywords)
	log.Printf("📊 Threads: %d\n", threads)
	log.Printf("💾 Output: %s\n", outputFile)
	
	// Start extraction
	err := extractOutlinks(archive, segments, filter, threads, outputFile)
	if err != nil {
		log.Fatalf("Extraction failed: %v", err)
	}
	
	log.Printf("✅ Extraction completed! Results saved to: %s\n", outputFile)
}

func handleBacklinksCommand() {
	// Parse command line arguments
	targetDomain := getArgValue("--target-domain")
	if targetDomain == "" {
		log.Println("Error: --target-domain parameter is required")
		os.Exit(1)
	}

	archive := getArgValue("--archive")
	if archive == "" {
		log.Println("Error: --archive parameter is required")
		os.Exit(1)
	}

	// Handle "latest" alias - resolve to most recent available archive
	if archive == "latest" {
		archive = "CC-MAIN-2024-10"  // Default to known working archive
		log.Printf("ℹ️  Resolving 'latest' to: %s\n", archive)
	}

	if !commoncrawl.IsCorrectArchiveFormat(archive) {
		log.Println("Error: Invalid archive format")
		os.Exit(1)
	}

	segments := getArgValue("--segments")
	if segments == "" {
		segments = "0" // Default to first segment
	}

	// Parse filter arguments
	// Support both --max-results and --limit (alias for compatibility)
	maxResults := getIntArg("--max-results", 0)
	if maxResults == 0 {
		maxResults = getIntArg("--limit", 0)
	}

	filter := OutlinkFilter{
		TargetDomains:    []string{targetDomain},  // Store target for output
		MinAnchorLength:  getIntArg("--min-anchor", 0),
		MaxResults:       maxResults,
		OutputFormat:     getArgValue("--format"),
	}

	// Parse list arguments manually
	if sourceTLDs := getArgValue("--source-tlds"); sourceTLDs != "" {
		filter.CountryTLDs = strings.Split(sourceTLDs, ",")
	}
	if sourceKeywords := getArgValue("--source-keywords"); sourceKeywords != "" {
		filter.URLKeywords = strings.Split(sourceKeywords, ",")
	}
	if exclude := getArgValue("--exclude"); exclude != "" {
		filter.ExcludeKeywords = strings.Split(exclude, ",")
	}

	if filter.OutputFormat == "" {
		filter.OutputFormat = "json"
	}

	threads := getIntArg("--threads", 2)
	outputFile := getArgValue("--output")

	// Default to stdout for piping to other processes (NDJSON format)
	// Use --output=filename.json to save to file instead
	useStdout := outputFile == "" || outputFile == "-" || outputFile == "stdout"
	if outputFile == "" {
		outputFile = "-"  // Marker for stdout
	}

	log.Printf("🔗 Starting backlink extraction...\n")
	log.Printf("📁 Archive: %s\n", archive)
	log.Printf("🎯 Target domain: %s\n", targetDomain)
	log.Printf("📊 Threads: %d\n", threads)
	log.Printf("💾 Output: %s\n\n", outputFile)

	// Start extraction
	err := extractBacklinks(targetDomain, archive, segments, filter, threads, outputFile)
	if err != nil {
		log.Fatalf("Backlink extraction failed: %v", err)
	}

	if !useStdout {
		log.Printf("✅ Backlink extraction completed! Results saved to: %s\n", outputFile)
	}
}

func extractBacklinks(targetDomain, archive, segments string, filter OutlinkFilter, threads int, outputFile string) error {
	log.Println("🚀 Entering extractBacklinks...")

	// Initialize Common Crawl data
	log.Println("📦 Calling commoncrawl.InitImport...")
	segmentList, err := commoncrawl.InitImport(archive)
	if err != nil {
		return fmt.Errorf("could not load segment list: %v", err)
	}
	log.Printf("✅ InitImport done. Loaded %d segments.\n", len(segmentList))

	// Parse segments
	segmentsToProcess, err := parseSegmentInput(segments)
	if err != nil {
		return fmt.Errorf("invalid segment input: %v", err)
	}
	log.Printf("🔢 Processing %d segments: %v\n", len(segmentsToProcess), segmentsToProcess)

	// Use stdout for piping, or create file
	useStdout := outputFile == "-" || outputFile == "stdout" || outputFile == ""
	var outFile *os.File
	if useStdout {
		outFile = os.Stdout
		// For stdout, use NDJSON format (one JSON object per line)
		filter.OutputFormat = "ndjson"
	} else {
		var err error
		outFile, err = os.Create(outputFile)
		if err != nil {
			return fmt.Errorf("could not create output file: %v", err)
		}
		defer outFile.Close()

		// Write header based on format
		if filter.OutputFormat == "csv" {
			outFile.WriteString("source_domain,source_url,target_domain,target_url,anchor_text,date_discovered,is_nofollow,matched_filter\n")
		} else if filter.OutputFormat == "json" {
			outFile.WriteString("[\n")
		}
	}

	var mutex sync.Mutex
	var wg sync.WaitGroup
	guard := make(chan struct{}, threads)

	resultCount := 0
	maxResults := filter.MaxResults

	// Process each segment
	for _, segmentID := range segmentsToProcess {
		if maxResults > 0 && resultCount >= maxResults {
			break
		}

		segment, err := commoncrawl.SelectSegmentByID(segmentList, segmentID)
		if err != nil {
			log.Printf("⚠️ Warning: Segment %d not found\n", segmentID)
			continue
		}

		log.Printf("🔄 Processing segment %d...\n", segmentID)

		// Process WAT files in this segment
	totalWATFiles := len(segment.WatFiles)
		log.Printf("📁 Segment %d has %d WAT files\n", segmentID, totalWATFiles)

		filesProcessed := 0
		for _, watFile := range segment.WatFiles {
			if maxResults > 0 && resultCount >= maxResults {
				break
			}

			filesProcessed++
			if filesProcessed%10 == 0 {
				log.Printf("   Processed %d/%d WAT files, found %d backlinks so far\n", filesProcessed, totalWATFiles, resultCount)
			} else {
				log.Printf("📄 Processing WAT file %d/%d: %s\n", filesProcessed, totalWATFiles, watFile.Path)
			}

			wg.Add(1)
			guard <- struct{}{}

			go func(watPath string, fileNum int) {
				defer wg.Done()
				defer func() { <-guard }()

				// Download and process WAT file for backlinks
				results, err := processWATFileForBacklinks(watPath, targetDomain, filter)
				if err != nil {
					log.Printf("❌ Error processing WAT file %s: %v", watPath, err)
					return
				}

				if len(results) > 0 {
					log.Printf("✅ Found %d backlinks in WAT file #%d\n", len(results), fileNum)
				}

				// Write results to file
				mutex.Lock()
				for _, result := range results {
					if maxResults > 0 && resultCount >= maxResults {
						break
					}
					writeResult(outFile, result, filter.OutputFormat, resultCount > 0)
					resultCount++
				}
				mutex.Unlock()

			}(watFile.Path, filesProcessed)
		}
	}

	log.Println("⏳ Waiting for threads to finish...")
	wg.Wait()
	log.Println("🏁 All threads finished.")

	// Close JSON array (only for file output, not NDJSON)
	if filter.OutputFormat == "json" {
		outFile.WriteString("\n]")
	}

	log.Printf("📊 Total backlinks extracted: %d\n", resultCount)
	return nil
}

func handleFilterCommand() {
	log.Println("🔍 Filter command - filters existing outlink data")
	
	inputFile := getArgValue("--input")
	if inputFile == "" {
		log.Println("Error: --input parameter is required")
		os.Exit(1)
	}
	
	filter := parseFilterArgs()
	outputFile := getArgValue("--output")
	if outputFile == "" {
		outputFile = "filtered_outlinks.json"
	}
	
	err := filterExistingData(inputFile, filter, outputFile)
	if err != nil {
		log.Fatalf("Filtering failed: %v", err)
	}
	
	log.Printf("✅ Filtering completed! Results saved to: %s\n", outputFile)
}

func handleSearchCommand() {
	log.Println("🔍 Search command - searches for specific outlink patterns")
	
	targetDomain := getArgValue("--target-domain")
	inputDir := getArgValue("--input")
	
	if targetDomain == "" || inputDir == "" {
		log.Println("Error: --target-domain and --input parameters are required")
		os.Exit(1)
	}
	
	err := searchOutlinks(targetDomain, inputDir)
	if err != nil {
		log.Fatalf("Search failed: %v", err)
	}
}

func extractOutlinks(archive, segments string, filter OutlinkFilter, threads int, outputFile string) error {
	// Initialize Common Crawl data
	segmentList, err := commoncrawl.InitImport(archive)
	if err != nil {
		return fmt.Errorf("could not load segment list: %v", err)
	}
	
	// Parse segments
	segmentsToProcess, err := parseSegmentInput(segments)
	if err != nil {
		return fmt.Errorf("invalid segment input: %v", err)
	}
	
	// Create output file
	outFile, err := os.Create(outputFile)
	if err != nil {
		return fmt.Errorf("could not create output file: %v", err)
	}
	defer outFile.Close()
	
	// Write header based on format
	if filter.OutputFormat == "csv" {
		outFile.WriteString("source_domain,source_url,target_domain,target_url,anchor_text,date_discovered,is_nofollow,matched_filter\n")
	} else if filter.OutputFormat == "json" {
		outFile.WriteString("[\n")
	}
	
	var mutex sync.Mutex
	var wg sync.WaitGroup
	guard := make(chan struct{}, threads)
	
	resultCount := 0
	
	// Process each segment
	for _, segmentID := range segmentsToProcess {
		segment, err := commoncrawl.SelectSegmentByID(segmentList, segmentID)
		if err != nil {
			continue
		}
		
		log.Printf("🔄 Processing segment %d...\n", segmentID)
		
		// Process WAT files in this segment
		for i, watFile := range segment.WatFiles {
			if i >= 5 { // Limit for testing
				break
			}
			
			wg.Add(1)
			guard <- struct{}{}
			
			go func(watPath string) {
				defer wg.Done()
				defer func() { <-guard }()
				
				// Download and process WAT file
				results, err := processWATFileForOutlinks(watPath, filter)
				if err != nil {
					log.Printf("Error processing WAT file %s: %v", watPath, err)
					return
				}
				
				// Write results to file
				mutex.Lock()
				for _, result := range results {
					writeResult(outFile, result, filter.OutputFormat, resultCount > 0)
					resultCount++
				}
				mutex.Unlock()
				
			}(watFile.Path)
		}
	}
	
	wg.Wait()
	
	// Close JSON array
	if filter.OutputFormat == "json" {
		outFile.WriteString("\n]")
	}
	
	log.Printf("📊 Total outlinks extracted: %d\n", resultCount)
	return nil
}

func processWATFileForOutlinks(watPath string, filter OutlinkFilter) ([]OutlinkResult, error) {
	var results []OutlinkResult
	
	// Create temp directory for WAT file
	tempDir := "temp_wat"
	err := fileutils.CreateDataDirectory(tempDir)
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(tempDir)
	
	// Download WAT file
	localWatFile := filepath.Join(tempDir, filepath.Base(watPath))
	err = fileutils.DownloadFile("https://data.commoncrawl.org/"+watPath, localWatFile, 2)
	if err != nil {
		return nil, fmt.Errorf("could not download WAT file: %v", err)
	}
	defer os.Remove(localWatFile)
	
	// Process WAT file line by line
	file, err := os.Open(localWatFile)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		
		// Parse line and extract page data
		watPage := commoncrawl.ParseWatLine(line)
		if watPage == nil {
			continue
		}
		
		// Check if this page is from one of our target domains
		if !isDomainMatch(watPage.URLRecord.Domain, filter.TargetDomains) {
			continue
		}
		
		// Extract outlinks that match our filters
		for _, link := range watPage.Links {
			if shouldIncludeOutlink(link, filter) {
				result := OutlinkResult{
					SourceDomain:   watPage.URLRecord.Domain,
					SourceURL:      reconstructURL(watPage.URLRecord),
					TargetDomain:   link.Domain,
					TargetURL:      reconstructURL(&link),
					AnchorText:     link.Text,
					DateDiscovered: *watPage.Imported,
					SourceIP:       *watPage.IP,
					IsNoFollow:     link.NoFollow == 1,
					RelevanceScore: calculateRelevanceScore(link, filter),
				}
			
				// Determine which filter matched
			result.MatchedFilter = getMatchedFilter(link, filter)
			
			results = append(results, result)
			
			// Limit results per domain
			if len(results) >= filter.MaxResults {
				break
			}
		}
		}
	}
	
	return results, nil
}

func processWATFileForBacklinks(watPath, targetDomain string, filter OutlinkFilter) ([]OutlinkResult, error) {
	var results []OutlinkResult

	// Create unique temp directory for this WAT file
	tempDir, err := os.MkdirTemp("", "wat_*")
	if err != nil {
		return nil, fmt.Errorf("could not create temp directory: %v", err)
	}
	defer os.RemoveAll(tempDir)

	// Download WAT file
	localWatFile := filepath.Join(tempDir, filepath.Base(watPath))
	err = fileutils.DownloadFile("https://data.commoncrawl.org/"+watPath, localWatFile, 2)
	if err != nil {
		return nil, fmt.Errorf("could not download WAT file: %v", err)
	}
	defer os.Remove(localWatFile)

	// Process WAT file line by line
	file, err := os.Open(localWatFile)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	pagesScanned := 0
	linksChecked := 0

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()

		// Parse line and extract page data
		watPage := commoncrawl.ParseWatLine(line)
		if watPage == nil {
			continue
		}

		pagesScanned++

		// KEY DIFFERENCE: Don't filter by source domain - check ALL pages
		// Apply source filters if specified
		if len(filter.CountryTLDs) > 0 {
			matched := false
			for _, tld := range filter.CountryTLDs {
				if strings.HasSuffix(watPage.URLRecord.Domain, tld) {
					matched = true
					break
				}
			}
			if !matched {
				continue
			}
		}

		// Check if source page URL contains required keywords
		if len(filter.URLKeywords) > 0 {
			sourceURL := reconstructURL(watPage.URLRecord)
			matched := false
			for _, keyword := range filter.URLKeywords {
				if strings.Contains(strings.ToLower(sourceURL), strings.ToLower(keyword)) {
					matched = true
					break
				}
			}
			if !matched {
				continue
			}
		}

		// Check if source page URL contains excluded keywords
		if len(filter.ExcludeKeywords) > 0 {
			sourceURL := reconstructURL(watPage.URLRecord)
			excluded := false
			for _, keyword := range filter.ExcludeKeywords {
				if strings.Contains(strings.ToLower(sourceURL), strings.ToLower(keyword)) {
					excluded = true
					break
				}
			}
			if excluded {
				continue
			}
		}

		// Now check if ANY link on this page points TO the target domain
		for _, link := range watPage.Links {
			linksChecked++

			if isDomainMatch(link.Domain, []string{targetDomain}) {
				// Check anchor text minimum length
				if len(link.Text) < filter.MinAnchorLength {
					continue
				}

				result := OutlinkResult{
					SourceDomain:   watPage.URLRecord.Domain,
					SourceURL:      reconstructURL(watPage.URLRecord),
					TargetDomain:   link.Domain,
					TargetURL:      reconstructURL(&link),
					AnchorText:     link.Text,
					DateDiscovered: *watPage.Imported,
					SourceIP:       *watPage.IP,
					IsNoFollow:     link.NoFollow == 1,
					RelevanceScore: calculateRelevanceScore(link, filter),
					MatchedFilter:  fmt.Sprintf("target:%s", targetDomain),
				}

				results = append(results, result)

				// Limit results if specified
				if filter.MaxResults > 0 && len(results) >= filter.MaxResults {
					log.Printf("📊 WAT file stats: %d pages scanned, %d links checked, %d backlinks found", pagesScanned, linksChecked, len(results))
					return results, nil
				}
			}
		}
	}

	if len(results) > 0 {
		log.Printf("📊 WAT file stats: %d pages scanned, %d links checked, %d backlinks found", pagesScanned, linksChecked, len(results))
	}

	return results, nil
}

func isDomainMatch(domain string, targetDomains []string) bool {
	for _, target := range targetDomains {
		if strings.Contains(domain, target) || strings.Contains(target, domain) {
			return true
		}
	}
	return false
}

func shouldIncludeOutlink(link commoncrawl.URLRecord, filter OutlinkFilter) bool {
	// Check country TLD filter
	if len(filter.CountryTLDs) > 0 {
		matched := false
		for _, tld := range filter.CountryTLDs {
			if strings.HasSuffix(link.Domain, tld) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}
	
	// Check URL keyword filter
	if len(filter.URLKeywords) > 0 {
		matched := false
		fullURL := reconstructURL(&link)
		for _, keyword := range filter.URLKeywords {
			if strings.Contains(strings.ToLower(fullURL), strings.ToLower(keyword)) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}
	
	// Check exclude keywords
	if len(filter.ExcludeKeywords) > 0 {
		fullURL := reconstructURL(&link)
		for _, keyword := range filter.ExcludeKeywords {
			if strings.Contains(strings.ToLower(fullURL), strings.ToLower(keyword)) {
				return false
			}
		}
	}
	
	// Check minimum anchor length
	if len(link.Text) < filter.MinAnchorLength {
		return false
	}
	
	return true
}

func calculateRelevanceScore(link commoncrawl.URLRecord, filter OutlinkFilter) int {
	score := 0
	
	// Base score
	score += 10
	
	// Anchor text quality
	if len(link.Text) > 10 {
		score += 5
	}
	if len(link.Text) > 25 {
		score += 5
	}
	
	// Domain quality
	if !link.IsSubdomain() {
		score += 10
	}
	
	// DoFollow bonus
	if link.NoFollow == 0 {
		score += 15
	}
	
	// Keyword matches in anchor text
	for _, keyword := range filter.URLKeywords {
		if strings.Contains(strings.ToLower(link.Text), strings.ToLower(keyword)) {
			score += 20
		}
	}
	
	return score
}

func getMatchedFilter(link commoncrawl.URLRecord, filter OutlinkFilter) string {
	var matches []string
	
	// Check which filters matched
	for _, tld := range filter.CountryTLDs {
		if strings.HasSuffix(link.Domain, tld) {
			matches = append(matches, fmt.Sprintf("tld:%s", tld))
		}
	}
	
	fullURL := reconstructURL(&link)
	for _, keyword := range filter.URLKeywords {
		if strings.Contains(strings.ToLower(fullURL), strings.ToLower(keyword)) {
			matches = append(matches, fmt.Sprintf("keyword:%s", keyword))
		}
	}
	
	return strings.Join(matches, ",")
}

func reconstructURL(record *commoncrawl.URLRecord) string {
	scheme := "http"
	if record.Scheme == "2" {
		scheme = "https"
	}
	
	url := fmt.Sprintf("%s://%s%s", scheme, record.Host, record.Path)
	if record.RawQuery != "" {
		url += "?" + record.RawQuery
	}
	
	return url
}

func writeResult(file *os.File, result OutlinkResult, format string, hasPrefix bool) {
	switch format {
	case "csv":
		file.WriteString(fmt.Sprintf("%s,%s,%s,%s,%q,%s,%t,%s\n",
			result.SourceDomain, result.SourceURL, result.TargetDomain, result.TargetURL,
			result.AnchorText, result.DateDiscovered, result.IsNoFollow, result.MatchedFilter))
	case "json":
		prefix := ""
		if hasPrefix {
			prefix = ","
		}
		// Use concatenation for multi-line string
		jsonStr := fmt.Sprintf("%s\n  {\n    \"source_domain\": %q,\n    \"source_url\": %q,\n    \"target_domain\": %q,\n    \"target_url\": %q,\n    \"anchor_text\": %q,\n    \"date_discovered\": %q,\n    \"is_nofollow\": %t,\n    \"matched_filter\": %q,\n    \"relevance_score\": %d\n  }",
			prefix, result.SourceDomain, result.SourceURL, result.TargetDomain, result.TargetURL,
			result.AnchorText, result.DateDiscovered, result.IsNoFollow, result.MatchedFilter, result.RelevanceScore)
		file.WriteString(jsonStr)
	case "ndjson":
		// NDJSON: One JSON object per line (for piping to other processes)
		file.WriteString(fmt.Sprintf("{\"source\":%q,\"target\":%q,\"anchorText\":%q,\"sourceDomain\":%q,\"targetDomain\":%q}\n",
			result.SourceURL, result.TargetURL, result.AnchorText, result.SourceDomain, result.TargetDomain))
	default: // txt
		file.WriteString(fmt.Sprintf("%s -> %s | %s | %s\n",
			result.SourceDomain, result.TargetDomain, result.AnchorText, result.MatchedFilter))
	}
}

func filterExistingData(inputFile string, filter OutlinkFilter, outputFile string) error {
	log.Printf("🔍 Filtering data from: %s\n", inputFile)

	// Open input file
	inFile, err := os.Open(inputFile)
	if err != nil {
		return fmt.Errorf("could not open input file: %v", err)
	}
	defer inFile.Close()

	// Create output file
	outFile, err := os.Create(outputFile)
	if err != nil {
		return fmt.Errorf("could not create output file: %v", err)
	}
	defer outFile.Close()

	scanner := bufio.NewScanner(inFile)
	// Increase buffer for large lines
	buf := make([]byte, 1024*1024)
	scanner.Buffer(buf, 1024*1024)

	kept := 0
	skipped := 0

	for scanner.Scan() {
		line := scanner.Text()
		if line == "" || line == "[" || line == "]" {
			continue
		}

		// Clean JSON array formatting
		line = strings.TrimPrefix(line, ",")
		line = strings.TrimSpace(line)

		var record OutlinkResult
		if err := json.Unmarshal([]byte(line), &record); err != nil {
			skipped++
			continue
		}

		// Apply filters
		if !passesFilter(record, filter) {
			skipped++
			continue
		}

		// Write to output (NDJSON format)
		jsonBytes, _ := json.Marshal(record)
		outFile.Write(jsonBytes)
		outFile.WriteString("\n")
		kept++
	}

	log.Printf("✅ Filtered: %d kept, %d skipped\n", kept, skipped)
	return nil
}

func passesFilter(record OutlinkResult, filter OutlinkFilter) bool {
	// TLD filter
	if len(filter.CountryTLDs) > 0 {
		matched := false
		for _, tld := range filter.CountryTLDs {
			if strings.HasSuffix(record.TargetDomain, tld) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	// URL keyword filter (include)
	if len(filter.URLKeywords) > 0 {
		matched := false
		urlLower := strings.ToLower(record.TargetURL)
		for _, kw := range filter.URLKeywords {
			if strings.Contains(urlLower, strings.ToLower(kw)) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	// Exclude keywords
	if len(filter.ExcludeKeywords) > 0 {
		urlLower := strings.ToLower(record.TargetURL)
		for _, kw := range filter.ExcludeKeywords {
			if strings.Contains(urlLower, strings.ToLower(kw)) {
				return false
			}
		}
	}

	// Anchor text minimum length
	if filter.MinAnchorLength > 0 && len(record.AnchorText) < filter.MinAnchorLength {
		return false
	}

	return true
}

func searchOutlinks(targetDomain, inputDir string) error {
	log.Printf("🔍 Searching for outlinks to: %s in %s\n", targetDomain, inputDir)

	// Find all NDJSON/JSON files in input directory
	var files []string
	err := filepath.Walk(inputDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Skip errors
		}
		if !info.IsDir() && (strings.HasSuffix(path, ".json") || strings.HasSuffix(path, ".ndjson")) {
			files = append(files, path)
		}
		return nil
	})
	if err != nil {
		return fmt.Errorf("could not walk input directory: %v", err)
	}

	if len(files) == 0 {
		return fmt.Errorf("no JSON/NDJSON files found in %s", inputDir)
	}

	log.Printf("📁 Found %d files to search\n", len(files))

	found := 0
	targetLower := strings.ToLower(targetDomain)

	for _, filePath := range files {
		file, err := os.Open(filePath)
		if err != nil {
			continue
		}

		scanner := bufio.NewScanner(file)
		buf := make([]byte, 1024*1024)
		scanner.Buffer(buf, 1024*1024)

		for scanner.Scan() {
			line := scanner.Text()
			if line == "" || line == "[" || line == "]" {
				continue
			}

			line = strings.TrimPrefix(line, ",")
			line = strings.TrimSpace(line)

			var record OutlinkResult
			if err := json.Unmarshal([]byte(line), &record); err != nil {
				continue
			}

			// Check if target domain matches
			if strings.Contains(strings.ToLower(record.TargetDomain), targetLower) ||
				strings.Contains(strings.ToLower(record.TargetURL), targetLower) {
				// Output as NDJSON to stdout
				jsonBytes, _ := json.Marshal(record)
				fmt.Println(string(jsonBytes))
				found++
			}
		}
		file.Close()
	}

	log.Printf("✅ Found %d links to %s\n", found, targetDomain)
	return nil
}

// Helper functions for argument parsing
func parseExtractArgs() OutlinkFilter {
	filter := OutlinkFilter{
		MinAnchorLength: 3,
		MaxResults:      1000,
		OutputFormat:    "json",
	}
	
	// Parse domains
	if domains := getArgValue("--domains"); domains != "" {
		filter.TargetDomains = strings.Split(domains, ",")
	}
	
	// Parse country TLDs
	if tlds := getArgValue("--country-tlds"); tlds != "" {
		filter.CountryTLDs = strings.Split(tlds, ",")
	}
	
	// Parse URL keywords
	if keywords := getArgValue("--url-keywords"); keywords != "" {
		filter.URLKeywords = strings.Split(keywords, ",")
	}
	
	// Parse exclude keywords
	if exclude := getArgValue("--exclude"); exclude != "" {
		filter.ExcludeKeywords = strings.Split(exclude, ",")
	}
	
	// Parse other options
	filter.MinAnchorLength = getIntArg("--min-anchor", 3)
	filter.MaxResults = getIntArg("--max-results", 1000)
	filter.OutputFormat = getArgValue("--format")
	if filter.OutputFormat == "" {
		filter.OutputFormat = "json"
	}
	filter.IncludeInternal = hasArg("--include-internal")
	
	return filter
}

func parseFilterArgs() OutlinkFilter {
	// Similar to parseExtractArgs but for filtering
	return parseExtractArgs()
}

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

func hasArg(arg string) bool {
	for _, a := range os.Args {
		if a == arg {
			return true
		}
	}
	return false
}

func parseSegmentInput(segments string) ([]int, error) {
	var results []int
	parts := strings.Split(segments, ",")
	if len(parts) > 1 {
		for _, part := range parts {
			result, err := strconv.Atoi(part)
			if err != nil {
				return nil, err
			}
			results = append(results, result)
		}
		return results, nil
	}

	if strings.Contains(segments, "-") {
		rangeParts := strings.Split(segments, "-")
		if len(rangeParts) != 2 {
			return nil, fmt.Errorf("invalid range: %s", segments)
		}
		start, err := strconv.Atoi(rangeParts[0])
		if err != nil {
			return nil, err
		}
		end, err := strconv.Atoi(rangeParts[1])
		if err != nil {
			return nil, err
		}
		if start > end {
			return nil, fmt.Errorf("invalid range: %s", segments)
		}
		for i := start; i <= end; i++ {
			results = append(results, i)
		}
		return results, nil
	}

	// Handling a single number
	number, err := strconv.Atoi(segments)
	if err != nil {
		return nil, err
	}
	results = append(results, number)

	return results, nil
}


// --- SNIPER MODE IMPLEMENTATION ---

// CCIndexRecord represents a record from the Common Crawl Index API
type CCIndexRecord struct {
	URL      string `json:"url"`
	Filename string `json:"filename"`
	Offset   string `json:"offset"`
	Length   string `json:"length"`
}

// Input record from Python script
type WatLocation struct {
	URL         string `json:"url"`
	WatFilename string `json:"wat_filename"`
}

func handleSniperCommand() {
	targetDomain := getArgValue("--target-domain")
	sourceDomainsStr := getArgValue("--source-domains")
	watListFile := getArgValue("--wat-list")
	archive := getArgValue("--archive")

	if targetDomain == "" {
		log.Fatal("Error: --target-domain is required")
	}
	
	// If wat-list is NOT provided, we need source-domains
	if watListFile == "" && sourceDomainsStr == "" {
		log.Fatal("Error: either --source-domains or --wat-list is required")
	}
	
	if archive == "" {
		archive = "CC-MAIN-2024-10" // Default to known working archive
		log.Printf("ℹ️  Using default archive: %s\n", archive)
	}

	threads := getIntArg("--threads", 4)
	outputFile := getArgValue("--output")
	
	// Output setup
	useStdout := outputFile == "" || outputFile == "-" || outputFile == "stdout"
	var outFile *os.File
	var err error
	
	if useStdout {
		outFile = os.Stdout
		outputFile = "-" 
	} else {
		outFile, err = os.Create(outputFile)
		if err != nil {
			log.Fatalf("Error creating output file: %v", err)
		}
		defer outFile.Close()
	}

	log.Printf("🔫 Starting SNIPER mode...\n")
	log.Printf("🎯 Target: %s\n", targetDomain)
	log.Printf("📁 Archive: %s\n", archive)

	watFiles := make(map[string][]string) // watFile -> [urls]

	if watListFile != "" {
		log.Printf("📂 Loading WAT list from: %s\n", watListFile)
		fileContent, err := os.ReadFile(watListFile)
		if err != nil {
			log.Fatalf("Error reading WAT list file: %v", err)
		}
		
		var locations []WatLocation
		if err := json.Unmarshal(fileContent, &locations); err != nil {
			log.Fatalf("Error parsing WAT list JSON: %v", err)
		}
		
		for _, loc := range locations {
			watFiles[loc.WatFilename] = append(watFiles[loc.WatFilename], loc.URL)
		}
		log.Printf("✅ Loaded %d locations from file\n", len(locations))
		
	} else {
		// Original Logic: Query CC Index
		sourceDomains := strings.Split(sourceDomainsStr, ",")
		log.Printf("🌐 Sources: %d domains\n", len(sourceDomains))
		
		// 1. Query CC Index for all source domains
		log.Println("🔍 Querying CC Index...")
		
		for _, source := range sourceDomains {
			// Trim whitespace
			source = strings.TrimSpace(source)
			if source == "" { continue }
			
			records, err := queryCCIndex(source, archive)
			if err != nil {
				log.Printf("⚠️  Error querying %s: %v\n", source, err)
				continue
			}
			
			if len(records) == 0 {
				log.Printf("⚠️  No records found for %s\n", source)
			}
			
			for _, rec := range records {
				// Convert WARC path to WAT path
				watPath := strings.Replace(rec.Filename, "/warc/", "/wat/", 1)
				watPath = strings.Replace(watPath, ".warc.gz", ".warc.wat.gz", 1)
				
				watFiles[watPath] = append(watFiles[watPath], rec.URL)
			}
		}
	}

	log.Printf("📦 Found pages distributed across %d WAT files\n", len(watFiles))
	// 2. Process WAT files
	var wg sync.WaitGroup
	guard := make(chan struct{}, threads)
	var mutex sync.Mutex
	
	resultCount := 0
	
	for watPath, urls := range watFiles {
		wg.Add(1)
		guard <- struct{}{}
		
		go func(path string, targetUrls []string) {
			defer wg.Done()
			defer func() { <-guard }()
			
			results, err := processWATSniper(path, targetDomain, targetUrls)
			if err != nil {
				log.Printf("❌ Error processing %s: %v\n", path, err)
				return
			}
			
			if len(results) > 0 {
				mutex.Lock()
				for _, r := range results {
					// Write NDJSON
					jsonBytes, _ := json.Marshal(r)
					outFile.Write(jsonBytes)
					outFile.WriteString("\n")
					resultCount++
				}
				mutex.Unlock()
				log.Printf("✅ Found %d links in %s\n", len(results), path)
			}
		}(watPath, urls)
	}
	
	wg.Wait()
	log.Printf("🏁 Sniper finished. Total backlinks: %d\n", resultCount)
}

func queryCCIndex(domain, archive string) ([]CCIndexRecord, error) {
	// Limit to 50 pages per domain to be fast ("sniper")
	url := fmt.Sprintf("https://index.commoncrawl.org/%s-index?url=%s/*&output=json&fl=url,filename,offset,length&limit=50", archive, domain)
	
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	
	var records []CCIndexRecord
	scanner := bufio.NewScanner(resp.Body)
	for scanner.Scan() {
		var rec CCIndexRecord
		if err := json.Unmarshal(scanner.Bytes(), &rec); err == nil {
			records = append(records, rec)
		}
	}
	return records, nil
}

func processWATSniper(watPath, targetDomain string, targetUrls []string) ([]OutlinkResult, error) {
	// Create target URL set for fast lookup
	targetUrlSet := make(map[string]bool)
	for _, u := range targetUrls {
		// Normalize: lower case, strip trailing slash
		norm := strings.ToLower(strings.TrimRight(u, "/"))
		targetUrlSet[norm] = true
	}

	// Create temp dir
	tempDir, err := os.MkdirTemp("", "wat_sniper_*")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(tempDir)
	
	localWatFile := filepath.Join(tempDir, filepath.Base(watPath))
	err = fileutils.DownloadFile("https://data.commoncrawl.org/"+watPath, localWatFile, 3) // 3 retries
	if err != nil {
		return nil, err
	}
	defer os.Remove(localWatFile)
	
	file, err := os.Open(localWatFile)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	
	var results []OutlinkResult
	scanner := bufio.NewScanner(file)
	
	// Buffer size increase for large lines
	const maxCapacity = 1024 * 1024 * 5 // 5MB
	buf := make([]byte, maxCapacity)
	scanner.Buffer(buf, maxCapacity)
	
	for scanner.Scan() {
		line := scanner.Text()
		
		// Quick pre-check: does this line contain our target domain?
		// Optimization: If the line doesn't mention the target domain, it can't have a link to it.
		if !strings.Contains(line, targetDomain) {
			continue 
		}

		watPage := commoncrawl.ParseWatLine(line)
		if watPage == nil {
			continue
		}
		
		// Check if this is one of the pages we are looking for (Source Page)
		sourceUrl := strings.ToLower(strings.TrimRight(watPage.URLRecord.URL, "/"))
		if !targetUrlSet[sourceUrl] {
			continue
		}
		
		// Check links
		for _, link := range watPage.Links {
			if isDomainMatch(link.Domain, []string{targetDomain}) {
				results = append(results, OutlinkResult{
					SourceDomain: watPage.URLRecord.Domain,
					SourceURL: watPage.URLRecord.URL,
					TargetDomain: link.Domain,
					TargetURL: reconstructURL(&link),
					AnchorText: link.Text,
					DateDiscovered: *watPage.Imported,
					MatchedFilter: "sniper",
				})
			}
		}
	}
	return results, nil
}
