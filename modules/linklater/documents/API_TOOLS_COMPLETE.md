# 🚀 LinkData API Tools - Complete Implementation!

**All queryable domain intelligence APIs now have interactive CLI tools!**

## 🎯 **What's Been Created**

### **Master Interface**

```bash
./linkdata_cli.py  # 🎛️ Unified access to all tools
```

### **Individual API Tools**

```bash
./cc_index_cli.py        # 🔍 Common Crawl Index API
./tranco_cli.py          # 🏆 Tranco Domain Rankings
./openpagerank_cli.py    # 📊 Open PageRank Scores
./cloudflare_radar_cli.py # 🛡️ Cloudflare Radar Intel
./bigquery_cli.py        # 📈 BigQuery Public Datasets
./globallinks/bin/outlinker # 🔗 Backlinks/Outlinks Analysis
```

## 🎮 **Quick Start**

### **Option 1: Master Interface (Recommended)**

```bash
cd /Users/attic/LinkData
./linkdata_cli.py
```

### **Option 2: Direct Tool Access**

```bash
# Check domain ranking
./tranco_cli.py --domain example.com

# Find Common Crawl files containing domain
./cc_index_cli.py --domain example.com

# Get PageRank score
./openpagerank_cli.py --domain example.com

# Get top domains by country
./cloudflare_radar_cli.py --top-domains --location US

# Query website technologies
./bigquery_cli.py --query "SELECT app FROM \`httparchive.technologies.2024_10_01\` WHERE NET.HOST(url)='example.com'"

# Find backlinks to domain
./globallinks/bin/outlinker backlinks --target-domain=example.com --archive=CC-MAIN-2024-10
```

## 🔧 **Setup Requirements**

### **Basic Dependencies**

```bash
pip install requests google-cloud-bigquery
```

### **API Keys (Optional but Recommended)**

```bash
# Open PageRank (200k requests/month free)
export OPENPAGERANK_API_KEY=your_key

# Cloudflare Radar (rate limited but free)
export CLOUDFLARE_API_TOKEN=your_token

# BigQuery (1TB/month free)
export GOOGLE_CLOUD_PROJECT=your_project_id
gcloud auth application-default login
```

### **Get API Keys**

- **Open PageRank**: https://openpagerank.com/
- **Cloudflare**: https://dash.cloudflare.com/profile/api-tokens
- **BigQuery**: https://cloud.google.com/bigquery

## 📋 **Complete Tool Comparison**

| Tool                   | Purpose                | Cost      | Limits         | Best For                |
| ---------------------- | ---------------------- | --------- | -------------- | ----------------------- |
| **Common Crawl Index** | Find domain files      | Free      | Unlimited      | Historical research     |
| **Tranco Rankings**    | Domain authority       | Free      | Unlimited      | Authority checking      |
| **Open PageRank**      | Authority scores       | Free tier | 200k/month     | Bulk authority analysis |
| **Cloudflare Radar**   | Internet insights      | Free tier | Rate limited   | Geographic analysis     |
| **BigQuery Datasets**  | Technology/performance | Free tier | 1TB/month      | Deep analysis           |
| **GlobalLinks**        | Backlinks/outlinks     | Free      | Download costs | Link discovery          |

## 🎯 **Use Case Examples**

### **🕵️ OSINT Investigation**

```bash
# 1. Check domain authority
./tranco_cli.py --domain target.com

# 2. Find government backlinks
./globallinks/bin/outlinker backlinks --target-domain=target.com --source-tlds=".gov,.mil"

# 3. Technology analysis
./bigquery_cli.py  # Then select HTTP Archive technology lookup

# 4. Geographic presence
./cloudflare_radar_cli.py  # Then select domain info
```

### **🏢 Competitor Analysis**

```bash
# 1. Compare rankings
./tranco_cli.py  # Then select multiple domain comparison

# 2. Authority comparison
./openpagerank_cli.py --domains "competitor1.com,competitor2.com,competitor3.com"

# 3. Technology stack comparison
./bigquery_cli.py  # Use technology lookup for each domain

# 4. Backlink analysis
./globallinks/bin/outlinker backlinks --target-domain=competitor.com
```

### **📈 Market Research**

```bash
# 1. Top domains in country
./cloudflare_radar_cli.py --top-domains --location US --limit 1000

# 2. Technology adoption trends
./bigquery_cli.py  # Query HTTP Archive for technology trends

# 3. Performance benchmarks
./bigquery_cli.py  # Query Chrome UX Report for performance data
```

### **🔗 Link Building Research**

```bash
# 1. Find competitor backlinks
./globallinks/bin/outlinker backlinks --target-domain=competitor.com --archive=CC-MAIN-2024-10

# 2. Check source authority
./openpagerank_cli.py  # Bulk check the backlink sources

# 3. Historical link analysis
./cc_index_cli.py --domain competitor.com  # Find historical data
```

## 🚀 **Advanced Features**

### **Bulk Processing**

- **Tranco**: Bulk domain ranking checks
- **Open PageRank**: Up to 100 domains per request
- **BigQuery**: SQL queries across millions of domains
- **GlobalLinks**: Parallel WAT file processing

### **Filtering & Targeting**

- **Geographic**: Country-specific results
- **Technology**: Filter by tech stack
- **Authority**: Minimum PageRank thresholds
- **Time-based**: Historical data analysis

### **Export Capabilities**

- **JSON**: Structured data export
- **CSV**: Spreadsheet-compatible
- **TXT**: Simple lists
- **SQL**: Direct database import

## 🎨 **Interactive Features**

### **Smart Wizards**

- **Quick Start**: Guided setup for common tasks
- **Tool Selection**: Recommends best tools for specific needs
- **Parameter Guidance**: Interactive parameter selection

### **Rich Output**

- **Progress Indicators**: Real-time processing status
- **Error Handling**: Clear error messages and suggestions
- **Context Help**: Built-in usage examples

### **Batch Operations**

- **File Input**: Process domain lists from files
- **Multi-tool Workflows**: Chain operations across tools
- **Result Correlation**: Cross-reference data between tools

## 🏆 **Key Advantages**

### **✅ Queryable Without Downloads**

- No need to download massive datasets
- Query specific domains instantly
- Pay only for what you need

### **✅ Comprehensive Coverage**

- Authority rankings (Tranco, PageRank)
- Geographic distribution (Cloudflare, CrUX)
- Technology analysis (HTTP Archive)
- Link relationships (Common Crawl)
- Performance data (Chrome UX Report)

### **✅ Cost Effective**

- Most tools have generous free tiers
- BigQuery: 1TB free processing/month
- Open PageRank: 200k requests/month
- Common Crawl: Unlimited queries

### **✅ Production Ready**

- Error handling and retry logic
- Rate limiting compliance
- Authentication management
- Progress monitoring

## 🎛️ **Master CLI Features**

The unified interface (`linkdata_cli.py`) provides:

1. **Tool Discovery**: See all available tools and their status
2. **Quick Launch**: Direct access to any tool
3. **Setup Guidance**: Configuration help and API key management
4. **Usage Examples**: Practical scenarios and command examples
5. **Tool Comparison**: Choose the right tool for your needs

## 📊 **Sample Outputs**

### **Domain Authority Check**

```
🎯 DOMAIN RANKING
Domain: example.com
Rank: #1,234
Context: ✅ Top 10K - Good authority
```

### **Backlinks Discovery**

```
🔗 BACKLINKS FOUND: 156
💾 Download size: 2.1GB
📁 WAT files needed: 7
🎯 Sample sources: bbc.com, guardian.com, gov.uk
```

### **Technology Analysis**

```
🔧 TECHNOLOGY STACK: example.com
• WordPress (CMS)
• React (JavaScript Framework)
• Cloudflare (CDN)
• Google Analytics (Analytics)
```

## 🎉 **All Tools Operational!**

**Every queryable API now has a complete, interactive CLI tool with:**

- ✅ Interactive menus and wizards
- ✅ Command-line direct usage
- ✅ Bulk processing capabilities
- ✅ Multiple output formats
- ✅ Error handling and validation
- ✅ Authentication management
- ✅ Usage examples and help

**Ready for immediate use in OSINT investigations, competitor research, market analysis, and academic studies!** 🚀
