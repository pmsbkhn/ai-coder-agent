package com.example.library.membership;

import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class MemberRegistrationTest {
    @Test
    void newMemberHasDefaultLimitAndActiveStatus() {
        MemberService service = new InMemoryMemberService();
        Member member = service.register("John Doe");
        assertEquals(5, member.getBorrowLimit());
        assertEquals(MemberStatus.ACTIVE, member.getStatus());
    }
}
