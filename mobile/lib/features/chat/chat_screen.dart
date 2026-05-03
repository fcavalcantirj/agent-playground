// Phase 25 Wave 1 stub — replaced by Wave 4 plan 25-07 (Chat).

import 'package:flutter/material.dart';

class ChatScreen extends StatelessWidget {
  const ChatScreen({required this.agentInstanceId, super.key});

  final String agentInstanceId;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text('Chat — $agentInstanceId')),
        body: const Center(child: Text('Chat — coming Wave 4')),
      );
}
