package com.example.sample;

import com.example.sample.application.OrderService;
import com.example.sample.config.CollectingEventSender;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import tech.vsf.ptnt.msfw.event.schema.cloudevent.CloudEvent;
import tech.vsf.ptnt.msfw.outbox.publication.OutboxEventPublisher;
import tech.vsf.ptnt.msfw.outbox.store.EventStore;
import tech.vsf.ptnt.msfw.outbox.store.OutboxEvent;

import java.math.BigDecimal;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Acceptance oracle for the `order-priority` task: placing an order with a
 * priority must carry that priority through the outbox into the published
 * CloudEvent (the real MSFW @EventPublishHandler outbox flow).
 */
@SpringBootTest
class OrderPriorityOutboxTest {

    @Autowired
    private OrderService orderService;          // framework proxy
    @Autowired
    private EventStore eventStore;
    @Autowired
    private OutboxEventPublisher publisher;
    @Autowired
    private CollectingEventSender sender;

    @Test
    void placingAnOrderWithPriority_carriesItThroughOutboxAndCloudEvent() {
        orderService.placeOrder("Dana", new BigDecimal("99000"), "HIGH");

        List<OutboxEvent<?>> stored = eventStore.allStoredEventsSince(0);
        assertFalse(stored.isEmpty(), "an outbox row should be appended");
        OutboxEvent<?> outboxEvent = stored.get(stored.size() - 1);
        assertEquals("OrderPlaced", outboxEvent.type().value());
        String payloadJson = String.valueOf(outboxEvent.data().value());
        assertTrue(payloadJson.contains("HIGH"),
                "priority must be serialized into the outbox payload, got: " + payloadJson);

        publisher.execute();

        assertFalse(sender.sent().isEmpty(), "publisher should emit a CloudEvent");
        CloudEvent<?> published = sender.sent().get(sender.sent().size() - 1);
        String publishedJson = String.valueOf(published.data().value());
        assertTrue(publishedJson.contains("HIGH"),
                "priority must reach the published CloudEvent, got: " + publishedJson);
    }
}
