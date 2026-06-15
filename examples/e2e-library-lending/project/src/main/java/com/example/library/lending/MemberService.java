package com.example.library.lending;

// façade – makes the interface visible in the lending package.
public interface MemberService extends com.example.library.membership.MemberService {
    // no extra methods; just inherits register/findMember/suspend
}
