package com.truthstream.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisConfig {

    private static final Logger logger = LoggerFactory.getLogger(RedisConfig.class);

    @Bean
    public RedisTemplate<String, String> redisTemplate(RedisConnectionFactory factory) {
        if (factory instanceof LettuceConnectionFactory) {
            LettuceConnectionFactory lcf = (LettuceConnectionFactory) factory;
            logger.info("Initializing RedisTemplate. Connecting to Redis at {}:{}", 
                lcf.getHostName(), lcf.getPort());
        } else {
            logger.info("Initializing RedisTemplate with factory: {}", factory.getClass().getName());
        }

        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(new StringRedisSerializer());
        template.setHashKeySerializer(new StringRedisSerializer());
        template.setHashValueSerializer(new StringRedisSerializer());
        template.afterPropertiesSet();
        return template;
    }

    @Bean
    public RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory factory) {
        RedisMessageListenerContainer container = new RedisMessageListenerContainer();
        container.setConnectionFactory(factory);
        container.setErrorHandler(t -> {
            logger.error("Error in Redis message listener: {}", t.getMessage(), t);
        });
        return container;
    }
}
