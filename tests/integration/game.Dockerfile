FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends minetest-server minetest-game ca-certificates && rm -rf /var/lib/apt/lists/* && useradd -u 1000 -m container
WORKDIR /home/container
COPY game-entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh
USER 1000:1000
ENTRYPOINT ["/entrypoint.sh"]
