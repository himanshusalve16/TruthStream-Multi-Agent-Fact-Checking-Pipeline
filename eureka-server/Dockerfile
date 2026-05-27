# ─────────────────────────────────────────────────────────────────────────────
# TruthStream Eureka Server — Dockerfile
#
# Multi-stage build:
#   Stage 1 (builder): Maven + JDK 21 compiles the jar
#   Stage 2 (runtime): Slim JRE 21 runs the jar
#
# Render deployment:
#   - Set Build Command: (empty — Docker handles the build)
#   - Set Start Command: (empty — CMD in Dockerfile handles it)
#   - Render injects $PORT automatically; application.yml reads ${PORT:8761}
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM maven:3.9.6-eclipse-temurin-21 AS builder

WORKDIR /build

# Copy POM first — cached layer unless pom.xml changes
COPY pom.xml .
RUN mvn dependency:go-offline -q

# Copy source and build
COPY src ./src
RUN mvn package -DskipTests -q

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

# Non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

COPY --from=builder /build/target/eureka-server-*.jar app.jar

# Render injects PORT at runtime; default 8761 for local Docker
EXPOSE ${PORT:-8761}

ENTRYPOINT ["java", \
  "-XX:+UseContainerSupport", \
  "-XX:MaxRAMPercentage=75.0", \
  "-Djava.security.egd=file:/dev/./urandom", \
  "-jar", "app.jar"]
