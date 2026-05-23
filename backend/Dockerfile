# ─────────────────────────────────────────────────────────────────────────────
# TruthStream Backend — Dockerfile
# Two-stage build: JDK build → JRE runtime
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jdk-alpine AS build

WORKDIR /app

# Copy Maven wrapper (Linux only — mvnw.cmd is Windows-only and unnecessary here)
COPY mvnw ./
COPY .mvn .mvn
COPY pom.xml ./

# Download all dependencies into the layer cache.
# This layer is only invalidated when pom.xml changes, not when source changes.
RUN chmod +x mvnw && ./mvnw dependency:go-offline -q --no-transfer-progress

# Now copy source and build
COPY src ./src
RUN ./mvnw package -DskipTests --no-transfer-progress -q

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre-alpine AS runtime

WORKDIR /app

# Non-root user
RUN addgroup -S spring && adduser -S spring -G spring
USER spring:spring

# Copy only the fat jar from the build stage
COPY --from=build /app/target/*.jar app.jar

EXPOSE 8080

# -XX:+UseContainerSupport  → JVM respects Docker memory limits
# -XX:MaxRAMPercentage=75.0 → Use up to 75% of container RAM for heap
# -Djava.security.egd=...   → Faster SecureRandom seed (avoids startup delay)
ENTRYPOINT ["java", \
  "-XX:+UseContainerSupport", \
  "-XX:MaxRAMPercentage=75.0", \
  "-Djava.security.egd=file:/dev/./urandom", \
  "-jar", "app.jar"]
