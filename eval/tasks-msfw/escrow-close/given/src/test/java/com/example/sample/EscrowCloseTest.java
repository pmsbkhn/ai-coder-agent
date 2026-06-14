package com.example.sample;

import com.example.sample.domain.escrow.Escrow;
import com.example.sample.domain.escrow.EscrowId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import tech.vsf.ptnt.msfw.domain.eventsourcing.EventSourcedRepository;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Acceptance oracle for the `escrow-close` task: closing is an event-sourced
 * command — its effect must come from a folded EscrowClosed event and survive
 * rehydration from the event stream.
 */
@SpringBootTest
class EscrowCloseTest {

    @Autowired
    private EventSourcedRepository<Escrow, EscrowId, Escrow.Memento> escrows;

    @Test
    void closingSettledEscrow_marksClosed_andSurvivesRehydration() {
        EscrowId id = new EscrowId("E-close-1");
        Escrow escrow = new Escrow(id);
        escrow.open();
        escrow.hold(100);
        escrow.release(100);   // settle: nothing left held
        escrow.close();
        escrows.save(escrow);

        Escrow loaded = escrows.load(id).orElseThrow();
        assertFalse(loaded.isOpen(), "a closed escrow must not be open after rehydration");
        assertEquals(4, loaded.version(), "open + hold + release + close = 4 events");
    }

    @Test
    void cannotCloseWithOutstandingHeldFunds() {
        Escrow escrow = new Escrow(new EscrowId("E-close-2"));
        escrow.open();
        escrow.hold(100);
        assertThrows(IllegalStateException.class, escrow::close);
    }

    @Test
    void cannotCloseAnEscrowThatWasNeverOpened() {
        Escrow escrow = new Escrow(new EscrowId("E-close-3"));
        assertThrows(IllegalStateException.class, escrow::close);
    }
}
