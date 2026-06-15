package com.example.library.lending;

import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class BorrowLimitExceededTest {
    @Test
    void cannotExceedBorrowLimit() {
        CatalogService catalog = new InMemoryCatalogService();
        Title title = new Title(UUID.randomUUID(), "ISBN-111", "Effective Java");
        catalog.addTitle(title);
        // create 5 copies and loan them to the member
        MemberService members = new InMemoryMemberService();
        Member member = members.register("Carol");
        LendingService lending = new InMemoryLendingService(catalog, members);
        for (int i = 0; i < 5; i++) {
            Copy copy = catalog.createCopy(title.getId());
            lending.createLoan(member.getId(), copy.getId(), LocalDate.now().minusDays(1));
        }
        // sixth copy
        Copy extraCopy = catalog.createCopy(title.getId());
        DomainException ex = assertThrows(DomainException.class,
            () -> lending.createLoan(member.getId(), extraCopy.getId(), LocalDate.now()));
        assertEquals(DomainException.Code.BORROW_LIMIT_EXCEEDED, ex.getCode());
    }
}
