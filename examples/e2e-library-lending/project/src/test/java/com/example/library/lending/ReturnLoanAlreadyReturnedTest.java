package com.example.library.lending;

import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ReturnLoanAlreadyReturnedTest {
    @Test
    void cannotReturnAlreadyReturnedLoan() {
        CatalogService catalog = new InMemoryCatalogService();
        Title title = new Title(UUID.randomUUID(), "ISBN-444", "Domain‑Driven Design");
        catalog.addTitle(title);
        Copy copy = catalog.createCopy(title.getId());
        MemberService members = new InMemoryMemberService();
        Member member = members.register("Frank");
        LendingService lending = new InMemoryLendingService(catalog, members);
        Loan loan = lending.createLoan(member.getId(), copy.getId(), LocalDate.now().minusDays(5));
        // first return – succeeds
        lending.returnLoan(loan.getId(), LocalDate.now());
        // second return – fails
        DomainException ex = assertThrows(DomainException.class,
            () -> lending.returnLoan(loan.getId(), LocalDate.now()));
        assertEquals(DomainException.Code.LOAN_ALREADY_RETURNED, ex.getCode());
    }
}
