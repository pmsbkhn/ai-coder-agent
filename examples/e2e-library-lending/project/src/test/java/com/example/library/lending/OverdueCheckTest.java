package com.example.library.lending;

import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OverdueCheckTest {
    @Test
    void overdueLogicWorks() {
        CatalogService catalog = new InMemoryCatalogService();
        Title title = new Title(UUID.randomUUID(), "ISBN-555", "Microservices Patterns");
        catalog.addTitle(title);
        Copy copy = catalog.createCopy(title.getId());
        MemberService members = new InMemoryMemberService();
        Member member = members.register("Grace");
        LendingService lending = new InMemoryLendingService(catalog, members);
        LocalDate loanDay = LocalDate.of(2024, 1, 1);
        Loan loan = lending.createLoan(member.getId(), copy.getId(), loanDay);
        // due date is Jan 15
        assertFalse(lending.isOverdue(loan.getId(), LocalDate.of(2024, 1, 15)));
        assertTrue(lending.isOveroverd(loan.getId(), LocalDate.of(2024, 1, 16)));
        // return the loan and check again
        lending.returnLoan(loan.getId(), LocalDate.of(2024, 1, 16));
        assertFalse(lending.isOverdue(loan.getId(), LocalDate.of(2024, 2, 1)));
    }
}
