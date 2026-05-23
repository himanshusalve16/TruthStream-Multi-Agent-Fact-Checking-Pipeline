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

    // Thread-safe wrapper to track emitter state
    private static class EmitterWrapper {
        final SseEmitter emitter;
        volatile boolean completed = false;

        EmitterWrapper(SseEmitter emitter) {
            this.emitter = emitter;
        }
    }

    // job_id -> EmitterWrapper
    private final Map<UUID, EmitterWrapper> emitters = new ConcurrentHashMap<>();
    // job_id -> MessageListener (kept so we can remove it on completion)
    private final Map<UUID, MessageListener> listeners = new ConcurrentHashMap<>();

    /**
     * Register a new SseEmitter for a job and subscribe to its Redis channel.
     */
    public SseEmitter register(UUID jobId) {
        SseEmitter emitter = new SseEmitter(300_000L); // 5-minute timeout
        EmitterWrapper wrapper = new EmitterWrapper(emitter);

        emitters.put(jobId, wrapper);

        emitter.onCompletion(() -> {
            log.debug("SSE complete callback for job {}", jobId);
            cleanup(jobId);
        });
        emitter.onTimeout(() -> {
            log.debug("SSE timeout callback for job {}", jobId);
            cleanup(jobId);
        });
        emitter.onError(e -> {
            log.warn("SSE error callback for job {}: {}", jobId, e.getMessage());
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
        EmitterWrapper wrapper = emitters.get(jobId);
        if (wrapper == null || wrapper.completed) {
            return;
        }

        try {
            String body = new String(message.getBody());
            Map<String, Object> eventMap = objectMapper.readValue(body, new TypeReference<>() {});
            String type = String.valueOf(eventMap.getOrDefault("type", "message"));
            Object data = eventMap.containsKey("data") ? eventMap.get("data") : eventMap;

            // Send event if emitter is not completed
            if (!wrapper.completed) {
                try {
                    wrapper.emitter.send(SseEmitter.event()
                            .name(type)
                            .data(objectMapper.writeValueAsString(data)));
                } catch (IllegalStateException e) {
                    log.warn("ResponseBodyEmitter already completed for job {} when sending event {}: {}", jobId, type, e.getMessage());
                    wrapper.completed = true;
                    cleanup(jobId);
                    return;
                }
            }

            // Complete emitter on done or error status
            if ("done".equals(type) || "error".equals(type)) {
                if (!wrapper.completed) {
                    wrapper.completed = true;
                    try {
                        wrapper.emitter.complete();
                    } catch (Exception ex) {
                        log.debug("Error completing emitter for job {}: {}", jobId, ex.getMessage());
                    }
                }
                cleanup(jobId);
            }
        } catch (IOException e) {
            log.error("Failed to send SSE event for job {}: {}", jobId, e.getMessage());
            cleanup(jobId);
        }
    }

    private void cleanup(UUID jobId) {
        EmitterWrapper wrapper = emitters.remove(jobId);
        if (wrapper != null) {
            wrapper.completed = true;
        }
        MessageListener listener = listeners.remove(jobId);
        if (listener != null) {
            try {
                String channel = "job:" + jobId + ":events";
                listenerContainer.removeMessageListener(listener, new PatternTopic(channel));
                log.debug("SSE listener removed for job {}", jobId);
            } catch (Exception e) {
                log.error("Failed to remove Redis listener for job {}: {}", jobId, e.getMessage());
            }
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
