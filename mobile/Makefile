.DEFAULT_GOAL := help
.PHONY: help install start ios android devices prebuild run device deploy typecheck bundle clean

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

devices:  ## List connected iPhones (copy a name for DEVICE=)
	xcrun devicectl list devices

prebuild:  ## Generate the native ios/ project (needs ios.bundleIdentifier in app.json)
	npx expo prebuild -p ios

run:  ## Build a dev build, then PICK a connected device or simulator to launch on
	npx expo run:ios --device

device:  ## Install on a cabled iPhone (debug; keeps Metro tethered). DEVICE="Name" to target one
	npx expo run:ios $(if $(DEVICE),--device "$(DEVICE)",--device)

deploy:  ## Install standalone on a cabled iPhone (release; runs untethered). DEVICE="Name" optional
	npx expo run:ios --configuration Release $(if $(DEVICE),--device "$(DEVICE)",--device)

typecheck:  ## Type-check with tsc (no emit)
	npx tsc --noEmit

bundle:  ## Headless production bundle — sanity check, no device needed
	npx expo export --platform ios --output-dir .expo-export

clean:  ## Clear Expo/Metro caches and bundles
	rm -rf .expo .expo-export
