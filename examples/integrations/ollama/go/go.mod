module github.com/nxus-SYSTEMS/nxusKit/examples/integrations/ollama

go 1.24.2

require github.com/nxus-SYSTEMS/nxusKit/packages/nxuskit-go v0.0.0

require github.com/nxus-SYSTEMS/nxusKit/examples/shared/go/interactive v0.0.0

require (
	al.essio.dev/pkg/shellescape v1.5.1 // indirect
	github.com/danieljoos/wincred v1.2.2 // indirect
	github.com/dustin/go-humanize v1.0.1 // indirect
	github.com/godbus/dbus/v5 v5.1.0 // indirect
	github.com/hbollon/go-edlib v1.7.0 // indirect
	github.com/mattn/go-isatty v0.0.20 // indirect
	github.com/zalando/go-keyring v0.2.6 // indirect
	golang.org/x/sys v0.41.0 // indirect
)

replace github.com/nxus-SYSTEMS/nxusKit/examples/shared/go/interactive => ../../../shared/go/interactive
