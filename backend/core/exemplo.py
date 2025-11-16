class MarcacaoHabitoViewSet(viewsets.ModelViewSet):
    serializer_class = MarcacaoHabitoSerializer

    def perform_create(self, serializer):
        # Garante que o usuario SEMPRE seja o do token, ignorando qualquer coisa do body
        serializer.save(usuario=self.request.user)

    def perform_update(self, serializer):
        # Mesma lógica para update
        serializer.save(usuario=self.request.user)

    def get_queryset(self):
        """
        Sempre lista só as marcações do usuário logado.
        Filtros suportados:
        - meta_id
        - data_inicio (AAAA-MM-DD)
        - data_fim (AAAA-MM-DD)
        """

        request = cast(Request, self.request)
        qs = (
        MarcacaoHabito.objects.select_related("meta", "usuario", "sessao")
        .filter(usuario=request.user)
        .order_by("data", "id")
        )

        # Filtro por meta
        meta_id = request.query_params.get("meta_id")
        if meta_id:
            qs = qs.filter(meta_id=meta_id)

        # Filtro por intervalo de datas
        data_inicio_str = request.query_params.get("data_inicio")
        data_fim_str = request.query_params.get("data_fim")

        if data_inicio_str:
            data_inicio = parse_date(data_inicio_str)
            if not data_inicio:
                raise ValidationError(
                {"data_inicio": "Data inválida. Use o formato AAAA-MM-DD."}
                )
            qs = qs.filter(data__gte=data_inicio)

        if data_fim_str:
            data_fim = parse_date(data_fim_str)
            if not data_fim:
                raise ValidationError(
                {"data_fim": "Data inválida. Use o formato AAAA-MM-DD."}
                )
            qs = qs.filter(data__lte=data_fim)


        return qs
