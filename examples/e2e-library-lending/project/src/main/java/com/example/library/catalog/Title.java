package com.example.library.catalog;

public class Title {
    private final String id;
    private final String isbn;
    private final String title;

    public Title(String id, String isbn, String title) {
        this.id = id;
        this.isbn = isbn;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }

    public String getTitle() {
        return title;
    }
}