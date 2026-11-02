/** "you", "the customer", "the business" or "the system": who cancelled a booking. */
export function cancelledByLabel(booking, currentUserId) {
  if (booking.cancelled_by == null) return 'the system (the reservation hold expired)'
  if (booking.cancelled_by === currentUserId) return 'you'
  if (booking.cancelled_by === booking.customer) return 'the customer'
  return 'the business'
}
