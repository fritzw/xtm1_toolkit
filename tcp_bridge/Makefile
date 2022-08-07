PORT ?= 23
CFLAGS := -Wall -Werror -pedantic -D LISTEN_PORT=$(PORT) $(MORE_CFLAGS)

all: tcp_bridge

tcp_bridge: tcp_bridge.c
	@echo "Building tcp_bridge for PORT=$(PORT)..."
	$(CC) $(CFLAGS) -o $@ $^
	@echo
	@echo "Now execute 'make setcap' if you configured a port below 1024."
	@echo

setcap: tcp_bridge
	@echo "Please enter your sudo password to grant $< access to ports below 1024."
	sudo setcap CAP_NET_BIND_SERVICE=+eip "$<"

clean:
	rm -f tcp_bridge
