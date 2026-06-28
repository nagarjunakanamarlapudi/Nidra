.DEFAULT_GOAL := help
.PHONY: help install start ios android typecheck bundle clean

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	npm install

start:  ## Start the Expo dev server (scan the QR with Expo Go)
	npx expo start

ios:  ## Launch the app in the iOS Simulator (Expo Go)
	npx expo start --ios

android:  ## Launch the app in the Android emulator (Expo Go)
	npx expo start --android

typecheck:  ## Type-check with tsc (no emit)
	npx tsc --noEmit

bundle:  ## Headless production bundle — sanity check, no device needed
	npx expo export --platform ios --output-dir .expo-export

clean:  ## Clear Expo/Metro caches and bundles
	rm -rf .expo .expo-export
