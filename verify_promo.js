// Promo System Verification Script
// Run this in the browser console on the landing page

console.log('🧪 Starting Promo System Verification...\n');

// Test 1: Check if pricing section exists
const pricingSection = document.getElementById('pricing');
console.log('✓ Test 1 - Pricing section exists:', !!pricingSection);

// Test 2: Check header link to pricing
const pricingLink = document.querySelector('a[href="#pricing"]');
console.log('✓ Test 2 - Header link to #pricing:', !!pricingLink);

// Test 3: Check pricing cards have required attributes
const priceCards = document.querySelectorAll('[data-plan]');
console.log('✓ Test 3 - Price cards with data-plan:', priceCards.length);

// Test 4: Check base prices
const basePrices = document.querySelectorAll('[data-base-price]');
basePrices.forEach(el => {
    console.log(`  - Card has base price: $${el.dataset.basePrice}`);
});

// Test 5: Check promo elements exist
const promoBadges = document.querySelectorAll('.promo-badge');
const priceStrikes = document.querySelectorAll('.price-strike');
const pricePromos = document.querySelectorAll('.price-promo');
console.log('✓ Test 5 - Promo elements:');
console.log(`  - Badges: ${promoBadges.length}`);
console.log(`  - Strike prices: ${priceStrikes.length}`);
console.log(`  - Promo prices: ${pricePromos.length}`);

// Test 6: Check promo form
const promoForm = document.querySelector('form[onsubmit*="handlePromoCodeSubmit"]');
console.log('✓ Test 6 - Promo form exists:', !!promoForm);

// Test 7: Test promo functions
console.log('\n📊 Testing Promo Functions:');
console.log('  - promoIsActive():', typeof promoIsActive === 'function' ? 'exists' : 'missing');
console.log('  - renderPromoPricing():', typeof renderPromoPricing === 'function' ? 'exists' : 'missing');
console.log('  - handlePromoCodeSubmit():', typeof handlePromoCodeSubmit === 'function' ? 'exists' : 'missing');

// Test 8: Current promo state
console.log('\n📌 Current State:');
console.log('  - Promo active:', promoIsActive());
console.log('  - URL has promo param:', new URLSearchParams(location.search).has('promo'));
console.log('  - localStorage has promo:', localStorage.getItem('cmr_promo_active'));

// Test 9: Simulate promo activation
console.log('\n🎯 Simulating Promo Activation:');
setPromoActive(true);
renderPromoPricing();
console.log('  - Activated promo via setPromoActive(true)');

setTimeout(() => {
    const visibleBadges = Array.from(document.querySelectorAll('.promo-badge')).filter(b => b.style.display !== 'none');
    const filledStrikes = Array.from(document.querySelectorAll('.price-strike')).filter(s => s.textContent.trim() !== '');
    const filledPromos = Array.from(document.querySelectorAll('.price-promo')).filter(p => p.textContent.trim() !== '');
    
    console.log('  - Visible badges:', visibleBadges.length);
    console.log('  - Filled strike prices:', filledStrikes.length);
    console.log('  - Filled promo prices:', filledPromos.length);
    
    // Clean up
    setPromoActive(false);
    renderPromoPricing();
    console.log('\n✅ Verification complete! Promo deactivated.');
}, 100);