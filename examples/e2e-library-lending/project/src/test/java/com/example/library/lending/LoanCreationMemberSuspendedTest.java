package com.example.library.lending;

import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class LoanCreationMemberSuspendedTest {
    @Test
    void suspendedMemberCannotBorrow() {
        // catalog with an available copy
        CatalogService catalog = new InMemoryCatalogService();
        Title title = new Title(UUID.randomUUID(), "ISBN-789", "Refactoring");
        catalog.addTitle(title);
        Copy copy = catalog.createCopy(title.getId());
        // member suspended
        MemberService members = new InMemoryMemberService();
        Member member = members.register("Bob");
        members.suspend(member.getId());
        LendingService lending = new InMemoryLendingService(catalog, members);
        DomainException ex = assertThrows(DomainException.class,
            () -> lending.createLoan(member.getId(), copy.getId(), LocalDate.now()));
        assertEquals(DomainException.Code.MEMBER_SUSPENDED, ex.getCode());
    }
}
