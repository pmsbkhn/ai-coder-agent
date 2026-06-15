package com.example.library.catalog;

import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class CopyCreationTest {
    @Test
    void copyIsCreatedWithAvailableStatus() {
        CatalogService catalog = new InMemoryCatalogService();
        Title title = new Title(UUID.randomUUID(), "ISBN-123", "Domain‑Driven Design");
        catalog.addTitle(title);
        Copy copy = catalog.createCopy(title.getId());
        assertEquals(CopyStatus.AVAILABLE, copy.getStatus());
    }
}
