package com.example.library.catalog;

import java.util.Map;
import java.util.HashMap;
import java.util.Objects;
import java.util.UUID;

public class InMemoryCatalogService implements CatalogService {
    private final Map<String, Title> titles = new HashMap<>();
    private final Map<String, Copy> copies = new HashMap<>();

    @Override
    public void addTitle(Title title) {
        titles.put(title.getId(), title);
    }

    @Override
    public Copy createCopy(String titleId) {
        Title title = titles.get(titleId);
        if (title == null) {
            throw new IllegalArgumentException("Title not found: " + titleId);
        }
        String copyId = UUID.randomUUID().toString();
        Copy copy = new Copy(copyId);
        copies.put(copyId, copy);
        return copy;
    }

    @Override
    public Copy findCopy(String copyId) {
        Copy c = copies.get(copyId);
        if (c == null) {
            throw new IllegalArgumentException("Copy not found: " + copyId);
        }
        return c;
    }
}
