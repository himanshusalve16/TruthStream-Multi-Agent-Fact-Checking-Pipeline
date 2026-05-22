package com.truthstream.service;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
public class RateLimitService {

    private final RedisTemplate<String, String> redisTemplate;

    @Value("${app.rate-limit.max-jobs-per-hour:10}")
    private int maxJobsPerHour;

    @Value("${app.rate-limit.max-auth-per-hour:20}")
    private int maxAuthPerHour;

    public void checkJobRateLimit(UUID userId) {
        String key = "ratelimit:jobs:" + userId;
        long count = readCount(key);
        if (count >= maxJobsPerHour) {
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,
                    "Rate limit exceeded: max " + maxJobsPerHour + " jobs per hour");
        }
    }

    public void recordJobSubmission(UUID userId) {
        incrementWithExpiry("ratelimit:jobs:" + userId, 1, TimeUnit.HOURS);
    }

    public void checkAuthRateLimit(String clientIp) {
        if (clientIp == null || clientIp.isBlank()) {
            return;
        }
        String key = "ratelimit:auth:" + clientIp;
        long count = readCount(key);
        if (count >= maxAuthPerHour) {
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,
                    "Too many authentication attempts. Try again later.");
        }
    }

    public void recordAuthAttempt(String clientIp) {
        if (clientIp == null || clientIp.isBlank()) {
            return;
        }
        incrementWithExpiry("ratelimit:auth:" + clientIp, 1, TimeUnit.HOURS);
    }

    private long readCount(String key) {
        String raw = redisTemplate.opsForValue().get(key);
        return raw != null ? Long.parseLong(raw) : 0;
    }

    private void incrementWithExpiry(String key, long ttl, TimeUnit unit) {
        Long count = redisTemplate.opsForValue().increment(key);
        if (count != null && count == 1) {
            redisTemplate.expire(key, ttl, unit);
        }
    }
}
