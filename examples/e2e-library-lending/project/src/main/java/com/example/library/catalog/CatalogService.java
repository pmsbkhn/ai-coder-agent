package com.example.library.catalog;

public interface CatalogService {
    void addTitle(Title title);
    Copy createCopy(String titleId);
    Copy findCopy(String copyId);
    java.util.List<Copy> findCopiesByTitle(String titleId);
}
