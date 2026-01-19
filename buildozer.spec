[app]

# App title
title = Flaxos Spaceship Sim

# Package name
package.name = flaxosspaceshipsim

# Package domain (needed for android/ios)
package.domain = org.flaxos

# Source code directory
source.dir = .

# Source files to include (comma separated, globs allowed)
source.include_exts = py,png,jpg,kv,atlas,json,yaml,yml,txt,md

# Source files to exclude (comma separated)
source.exclude_exts = spec

# Exclude directories
source.exclude_dirs = tests, bin, .git, .github, __pycache__, venv, build, dist

# Application versioning
version.regex = "version":\s*"([^"]+)"
version.filename = %(source.dir)s/version.json

# Application entry point
source.main = pydroid_run.py

# Requirements
# Comma separated list of Python modules/packages
requirements = python3,kivy,flask,numpy,pyyaml

# Supported orientations: landscape, portrait, all
orientation = landscape

# Android permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

# Android API
android.api = 31

# Minimum API required
android.minapi = 21

# Android NDK version
android.ndk = 25b

# Android SDK version
android.sdk = 31

# Android architecture
android.archs = arm64-v8a, armeabi-v7a

# Android app theme
android.theme = @android:style/Theme.NoTitleBar

# Presplash settings
presplash.filename = %(source.dir)s/mobile_ui/static/icon.png

# Icon settings
icon.filename = %(source.dir)s/mobile_ui/static/icon.png

# Supported platforms
supported_platforms = android

# Android bootstrap (use SDL2 for Kivy or webview for Flask)
# For Flask app, we'll use a webview
p4a.bootstrap = webview

# P4A (Python-for-Android) recipe
# Custom recipe for Flask app
p4a.local_recipes = ./android_recipes

# Services (background processes)
# Note: Flask server will run as a service
services = FlaskServer:pydroid_run.py

# Wakelock to keep app running
android.wakelock = True

# Whitelist for binary files
android.whitelist = lib-dynload/*.so

# Add Java classes
android.add_src = android_src

# Gradle dependencies
android.gradle_dependencies =

# App description
android.meta_data = "description:Flaxos Spaceship Simulator - Hard sci-fi space combat and navigation sim"

[buildozer]

# Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# Display warning if buildozer is run as root
warn_on_root = 1

# Build directory
build_dir = ./.buildozer

# Binary directory
bin_dir = ./bin
