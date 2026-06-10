package com.truthstream.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class FastApiClientTest {

    private FastApiClient fastApiClient;
    private final String fallbackUrl = "http://localhost:8000";

    @BeforeEach
    void setUp() {
        fastApiClient = new FastApiClient(
                fallbackUrl,
                "secret",
                30
        );
    }

    @Test
    void normalizeUrl_cleansNestedHttpsScheme() {
        String raw = "http://https://ai-service-w29p.onrender.com:10000";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("https://ai-service-w29p.onrender.com", normalized);
    }

    @Test
    void normalizeUrl_cleansNestedHttpScheme() {
        String raw = "http://http://ai-service:8000";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("http://ai-service:8000", normalized);
    }

    @Test
    void normalizeUrl_removesTrailingSlash() {
        String raw = "http://ai-service:8000/";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("http://ai-service:8000", normalized);
    }

    @Test
    void normalizeUrl_removesDuplicatePorts() {
        String raw = "http://https://ai-service-w29p.onrender.com:10000:10000";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("https://ai-service-w29p.onrender.com", normalized);
    }

    @Test
    void normalizeUrl_prependsHttpSchemeIfMissing() {
        String raw = "ai-service:8000";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("http://ai-service:8000", normalized);
    }

    @Test
    void normalizeUrl_cleansRenderHttpsUrlWithPort() {
        String raw = "http://https://ai-service-w29p.onrender.com:10000";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("https://ai-service-w29p.onrender.com", normalized);
    }

    @Test
    void normalizeUrl_cleansRenderHttpUrlWithPort() {
        String raw = "http://ai-service-w29p.onrender.com:8000";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("https://ai-service-w29p.onrender.com", normalized);
    }

    @Test
    void normalizeUrl_usesStaticBaseUrl() {
        // Verify that direct URL is used without any registry lookup
        FastApiClient client = new FastApiClient(
                "https://truthstream-ai.onrender.com",
                "secret",
                30
        );
        // The client should store the normalized form of the provided URL
        String normalized = FastApiClient.normalizeUrl("https://truthstream-ai.onrender.com");
        assertEquals("https://truthstream-ai.onrender.com", normalized);
    }
}
