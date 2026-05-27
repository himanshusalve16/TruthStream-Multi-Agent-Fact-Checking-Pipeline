package com.truthstream.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * HTTP client for the FastAPI AI Execution Service.
 *
 * <p>URL Resolution Strategy (in priority order):
 * <ol>
 *   <li>Eureka: {@link DiscoveryClient#getInstances} for service name
 *       {@code truthstream-ai-service} — used when Eureka is reachable.</li>
 *   <li>Static fallback: {@code FASTAPI_BASE_URL} env var — used when Eureka
 *       is unavailable (Render free-tier sleep, cold-start lag, etc.).</li>
 * </ol>
 *
 * <p>The WebClient is built without a base URL so that {@link #resolveBaseUrl()}
 * can be called fresh on each request without rebuilding the client.
 */
@Service
@Slf4j
public class FastApiClient {

    /**
     * Eureka service ID that the FastAPI service registers under.
     * Must be UPPERCASE — Eureka stores all app names in uppercase internally.
     * py-eureka-client registers as "truthstream-ai-service" which Eureka
     * canonicalises to "TRUTHSTREAM-AI-SERVICE". Using the uppercase form here
     * guarantees correct lookup on all Spring Cloud builds.
     */
    private static final String AI_SERVICE_ID = "TRUTHSTREAM-AI-SERVICE";

    private final WebClient webClient;
    private final String fallbackBaseUrl;
    private final String internalSecret;
    private final int timeoutSeconds;
    private final DiscoveryClient discoveryClient;

    public FastApiClient(
            @Value("${app.fastapi.base-url}") String fallbackBaseUrl,
            @Value("${app.internal.api-secret}") String internalSecret,
            @Value("${app.fastapi.timeout-seconds:30}") int timeoutSeconds,
            DiscoveryClient discoveryClient) {
        this.fallbackBaseUrl = fallbackBaseUrl;
        this.internalSecret = internalSecret;
        this.timeoutSeconds = timeoutSeconds;
        this.discoveryClient = discoveryClient;

        // Build WITHOUT a base URL — each request resolves its own URL via
        // resolveBaseUrl() so Eureka discoveries take effect immediately.
        this.webClient = WebClient.builder()
                .defaultHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .build();
    }

    // ── URL Resolution ────────────────────────────────────────────────────────

    /**
     * Resolve the base URL for the AI service.
     *
     * <p>Tries Eureka first. If the registry is unreachable or returns no
     * instances (e.g., free-tier service is sleeping), falls back to the
     * static {@code FASTAPI_BASE_URL} environment variable.
     */
    String resolveBaseUrl() {
        String rawUrl = null;
        try {
            List<ServiceInstance> instances = discoveryClient.getInstances(AI_SERVICE_ID);
            if (instances != null && !instances.isEmpty()) {
                rawUrl = instances.get(0).getUri().toString();
                log.info("Eureka-discovered URI: {}", rawUrl);
            } else {
                log.info("Eureka returned no instances for {}. Using static fallback URL: {}", AI_SERVICE_ID, fallbackBaseUrl);
            }
        } catch (Exception e) {
            log.warn("Eureka lookup failed for {}: {}. Using static fallback URL: {}", AI_SERVICE_ID, e.getMessage(), fallbackBaseUrl);
        }

        String finalUrl = normalizeUrl(rawUrl != null ? rawUrl : fallbackBaseUrl);
        log.info("Final normalized dispatch URL: {}", finalUrl);
        return finalUrl;
    }

    public static String normalizeUrl(String url) {
        if (url == null) {
            return null;
        }
        String normalized = url.trim();

        // Remove trailing slashes
        while (normalized.endsWith("/")) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }

        // Clean up nested schemes like http://https://, http://http://, https://https://, or https://http://
        if (normalized.startsWith("http://https://")) {
            normalized = normalized.substring(7);
        } else if (normalized.startsWith("http://http://")) {
            normalized = normalized.substring(7);
        } else if (normalized.startsWith("https://https://")) {
            normalized = normalized.substring(8);
        } else if (normalized.startsWith("https://http://")) {
            normalized = normalized.substring(8);
        }

        // If it does not start with http:// or https://, prepend http://
        if (!normalized.startsWith("http://") && !normalized.startsWith("https://")) {
            normalized = "http://" + normalized;
        }

        // Remove duplicate ports if they were appended at the end (e.g. host:10000:10000)
        normalized = normalized.replaceAll(":(\\d+):\\1$", ":$1");

        // Render deployment specific normalization: force HTTPS and strip port
        if (normalized.contains(".onrender.com")) {
            if (normalized.startsWith("http://")) {
                normalized = "https://" + normalized.substring(7);
            }
            normalized = normalized.replaceAll(":\\d+$", "");
        }

        return normalized;
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Dispatch a job to the FastAPI AI service. Non-blocking fire-and-forget.
     * The AI service will process the job asynchronously and publish events
     * back to the Gateway via Redis Pub/Sub.
     */
    public void dispatchJob(UUID jobId, UUID userId, String inputType, String url, String text) {
        Map<String, Object> body = new java.util.HashMap<>();
        body.put("job_id", jobId.toString());
        body.put("user_id", userId.toString());
        body.put("input_type", inputType);
        if (url != null) body.put("url", url);
        if (text != null) body.put("text", text);

        String baseUrl = resolveBaseUrl();

        webClient.post()
                .uri(baseUrl + "/internal/jobs")
                .header("X-Internal-Secret", internalSecret)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .onErrorResume(e -> {
                    log.error("Failed to dispatch job {} to AI service at {}: {}", jobId, baseUrl, e.getMessage());
                    return Mono.empty();
                })
                .subscribe(response ->
                        log.info("Job {} dispatched to AI service ({}), status: {}",
                                jobId, baseUrl, response != null ? response.getStatusCode() : "null")
                );
    }

    /**
     * Check if the FastAPI service is ready.
     * Uses Eureka-resolved URL with fallback.
     */
    public Mono<String> checkReady() {
        String baseUrl = resolveBaseUrl();
        return webClient.get()
                .uri(baseUrl + "/ready")
                .retrieve()
                .bodyToMono(Map.class)
                .map(responseBody -> {
                    if (responseBody != null && "ready".equals(responseBody.get("status"))) {
                        return "ready";
                    }
                    if (responseBody != null && "waking".equals(responseBody.get("status"))) {
                        return "waking";
                    }
                    return "sleeping";
                })
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(e -> {
                    log.debug("AI service /ready not responding at {}: {}", baseUrl, e.getMessage());
                    return Mono.just("sleeping");
                });
    }

    /**
     * Check if the FastAPI service is healthy.
     * Uses Eureka-resolved URL with fallback.
     */
    public Mono<String> checkHealth() {
        String baseUrl = resolveBaseUrl();
        return webClient.get()
                .uri(baseUrl + "/health")
                .retrieve()
                .bodyToMono(Map.class)
                .map(responseBody -> {
                    if (responseBody != null) {
                        String status = (String) responseBody.get("status");
                        if ("ok".equals(status)) {
                            return "healthy";
                        } else if ("degraded".equals(status)) {
                            return "degraded";
                        }
                    }
                    return "sleeping";
                })
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(e -> {
                    log.debug("AI service /health not responding at {}: {}", baseUrl, e.getMessage());
                    return Mono.just("sleeping");
                });
    }
}
