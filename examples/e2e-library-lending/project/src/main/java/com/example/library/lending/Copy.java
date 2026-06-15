package com.example.library.lending;

// façade – the tests expect a class named Copy in this package.
// It just extends the real domain object that lives in catalog.
public class Copy extends com.example.library.catalog.Copy {

    public Copy(String id) {
        super(id);
    }
}
