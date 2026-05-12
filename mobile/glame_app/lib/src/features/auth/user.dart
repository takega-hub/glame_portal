class User {
  final String id;
  final String? email;
  final String? phone;
  final String? fullName;
  final bool isCustomer;
  final int loyaltyPoints;

  const User({
    required this.id,
    required this.email,
    required this.phone,
    required this.fullName,
    required this.isCustomer,
    required this.loyaltyPoints,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: (json['id'] as String?) ?? '',
      email: json['email'] as String?,
      phone: json['phone'] as String?,
      fullName: json['full_name'] as String?,
      isCustomer: (json['is_customer'] as bool?) ?? true,
      loyaltyPoints: (json['loyalty_points'] as int?) ?? 0,
    );
  }
}
