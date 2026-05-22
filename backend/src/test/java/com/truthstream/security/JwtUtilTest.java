package com.truthstream.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class JwtUtilTest {

    private JwtUtil jwtUtil;

    @BeforeEach
    void setUp() {
        jwtUtil = new JwtUtil();
        ReflectionTestUtils.setField(jwtUtil, "secret",
                "test-secret-must-be-at-least-256-bits-long-for-hs256-signing-key-requirement-abc123xyz");
        ReflectionTestUtils.setField(jwtUtil, "expiryMs", 3_600_000L);
        jwtUtil.init();
    }

    @Test
    void generatesAndValidatesToken() {
        UUID userId = UUID.randomUUID();
        String token = jwtUtil.generateToken(userId, "user@example.com");

        assertTrue(jwtUtil.isTokenValid(token));
        assertEquals(userId, jwtUtil.extractUserId(token));
        assertEquals("user@example.com", jwtUtil.extractEmail(token));
    }

    @Test
    void rejectsInvalidToken() {
        assertFalse(jwtUtil.isTokenValid("not.a.valid.jwt"));
    }
}
