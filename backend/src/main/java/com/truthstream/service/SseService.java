package com.truthstream.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
@RequiredArgsConstructor
@Slf4j
public class SseService {

    private final RedisTemplate<String, String> redisTemplate;
    private final RedisMessageListenerContainer listenerContainer;
    private final ObjectMapper objectMapper;

    // job_id -> SseEmitter
    private final Map<UUID, SseEmitter> emitters = new ConcurrentHashMap<>();
    // job_id -> MessageListener (kept so we can remove it on completion)
    private final Map<UUID, MessageListener> listeners = new ConcurrentHashMap<>();

    /**
     * Register a new SseEmitter for a job and subscribe to its Redis channel.
     */
    public SseEmitter register(UUID jobId) {
        SseEmitter emitter = new SseEmitter(300_000L); // 5-minute timeout

        emitters.put(jobId, emitter);

        emitter.onCompletion(() -> cleanup(jobId));
        emitter.onTimeout(() -> {
            log.debug("SSE timeout for job {}", jobId);
            cleanup(jobId);
        });
        emitter.onError(e -> {
            log.warn("SSE error for job {}: {}", jobId, e.getMessage());
            cleanup(jobId);
        });

        // Subscribe to Redis channel for this job
        String channel = "job:" + jobId + ":events";
        MessageListener listener = (message, pattern) -> handleRedisMessage(jobId, message);
        listeners.put(jobId, listener);
        listenerContainer.addMessageListener(listener, new PatternTopic(channel));

        log.info("SSE registered for job {} on channel {}", jobId, channel);
        return emitter;
    }

    private void handleRedisMessage(UUID jobId, Message message) {
        SseEmitter emitter = emitters.get(jobId);
        if (emitter == null) {
            return;
        }

        try {
            String body = new String(message.getBody());
            Map<String, Object> eventMap = objectMapper.readValue(body, new TypeReference<>() {});
            String type = String.valueOf(eventMap.getOrDefault("type", "message"));
            Object data = eventMap.containsKey("data") ? eventMap.get("data") : eventMap;

            emitter.send(SseEmitter.event()
                    .name(type)
                    .data(objectMapper.writeValueAsString(data)));

            if ("done".equals(type) || "error".equals(type)) {
                emitter.complete();
                cleanup(jobId);
            }
        } catch (IOException e) {
            log.error("Failed to send SSE event for job {}: {}", jobId, e.getMessage());
            cleanup(jobId);
        }
    }

    private void cleanup(UUID jobId) {
        emitters.remove(jobId);
        MessageListener listener = listeners.remove(jobId);
        if (listener != null) {
            String channel = "job:" + jobId + ":events";
            listenerContainer.removeMessageListener(listener, new PatternTopic(channel));
        }
        log.debug("SSE cleaned up for job {}", jobId);
    }

    /**
     * Directly publish an event to a job channel (used for local testing).
     */
    public void publishEvent(UUID jobId, String type, Object data) {
        try {
            String channel = "job:" + jobId + ":events";
            Map<String, Object> event = Map.of("type", type, "data", data);
            redisTemplate.convertAndSend(channel, objectMapper.writeValueAsString(event));
        } catch (Exception e) {
            log.error("Failed to publish event for job {}: {}", jobId, e.getMessage());
        }
    }
}
