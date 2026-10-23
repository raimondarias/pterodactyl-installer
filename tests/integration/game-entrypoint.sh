#!/bin/sh
export HOME=/home/container
cd /home/container || exit 1
if [ ! -f minetest.conf ]; then printf '%s\n' 'server_announce = false' 'server_name = Installer isolated test' > minetest.conf; fi
STARTUP=$(printf '%s' "$STARTUP" | sed "s/{{SERVER_PORT}}/${SERVER_PORT}/g")
exec /bin/sh -c "exec $STARTUP --config /home/container/minetest.conf --logfile /home/container/minetest.log"
