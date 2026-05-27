package com.truthstream.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class FastApiClientTest {

    @Mock
    private DiscoveryClient discoveryClient;

    private FastApiClient fastApiClient;
    private final String fallbackUrl = "http://localhost:8000";

    @BeforeEach
    void setUp() {
        fastApiClient = new FastApiClient(
                fallbackUrl,
                "secret",
                30,
                discoveryClient
        );
    }

    @Test
    void normalizeUrl_cleansNestedHttpsScheme() {
        String raw = "http://https://ai-service-w29p.onrender.com:10000";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("https://ai-service-w29p.onrender.com:10000", normalized);
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
        assertEquals("https://ai-service-w29p.onrender.com:10000", normalized);
    }

    @Test
    void normalizeUrl_prependsHttpSchemeIfMissing() {
        String raw = "ai-service:8000";
        String normalized = FastApiClient.normalizeUrl(raw);
        assertEquals("http://ai-service:8000", normalized);
    }

    @Test
    void resolveBaseUrl_fallsBackWhenEurekaReturnsNoInstances() {
        when(discoveryClient.getInstances("TRUTHSTREAM-AI-SERVICE"))
                .thenReturn(Collections.emptyList());

        String resolved = fastApiClient.resolveBaseUrl();
        assertEquals("http://localhost:8000", resolved);
    }

    @Test
    void resolveBaseUrl_resolvesEurekaHttpsUri() {
        ServiceInstance instance = new DefaultServiceInstance(
                "instanceId", "TRUTHSTREAM-AI-SERVICE", "https://ai-service-w29p.onrender.com", 10000, true
        );
        when(discoveryClient.getInstances("TRUTHSTREAM-AI-SERVICE"))
                .thenReturn(List.of(instance));

        String resolved = fastApiClient.resolveBaseUrl();
        assertEquals("https://ai-service-w29p.onrender.com:10000", resolved);
    }

    @Test
    void resolveBaseUrl_resolvesEurekaHttpUri() {
        ServiceInstance instance = new DefaultServiceInstance(
                "instanceId", "TRUTHSTREAM-AI-SERVICE", "ai-service", 8000, false
        );
        when(discoveryClient.getInstances("TRUTHSTREAM-AI-SERVICE"))
                .thenReturn(List.of(instance));

        String resolved = fastApiClient.resolveBaseUrl();
        assertEquals("http://ai-service:8000", resolved);
    }
}
