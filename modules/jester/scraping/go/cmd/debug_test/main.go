package main

import (
	"fmt"
	"os"
	"time"

	"github.com/kris-dev-hub/globallinks/pkg/commoncrawl"
)

func main() {
	fmt.Println("🚀 Starting debug test...")
	start := time.Now()

	segments, err := commoncrawl.InitImport("CC-MAIN-2024-10")
	if err != nil {
		fmt.Printf("❌ Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("✅ Success! Found %d segments in %v\n", len(segments), time.Since(start))
}

