import discord
from discord.ext import commands
import json
import os

# ================== ARQUIVO DB ==================
DB_FILE = "database.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "config": {
                "pix": "Não configurado",
                "cargo_owner": None,
                "cat_suporte": None
            },
            "produtos": {}
        }
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

db = load_db()

# ================== BOT ==================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# ================== VIEW REDIRECIONAMENTO ==================
class RedirectView(discord.ui.View):
    def __init__(self, url):
        super().__init__()
        self.add_item(discord.ui.Button(label="Clique aqui", url=url, style=discord.ButtonStyle.link))

# ================== VIEW ADMIN ==================
class AdminActions(discord.ui.View):
    def __init__(self, cliente_id, produto_nome, cargo_id):
        super().__init__(timeout=None)
        self.cliente_id = cliente_id
        self.produto = produto_nome
        self.cargo_id = cargo_id

    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id == db["config"]["cargo_owner"] for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

        membro = interaction.guild.get_member(self.cliente_id)
        cargo = interaction.guild.get_role(self.cargo_id)

        if membro and cargo:
            await membro.add_roles(cargo)
            await interaction.response.send_message(
                f"✅ Pagamento aprovado!\n{membro.mention} recebeu **{self.produto}**"
            )
        else:
            await interaction.response.send_message("Erro ao entregar o produto.", ephemeral=True)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id == db["config"]["cargo_owner"] for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

        await interaction.response.send_message("❌ Pagamento recusado.")

    @discord.ui.button(label="Fechar Carrinho", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id == db["config"]["cargo_owner"] for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

        await interaction.channel.delete()

# ================== VIEW COMPRA ==================
class BuyView(discord.ui.View):
    def __init__(self, produto_nome, cargo_id):
        super().__init__(timeout=None)
        self.produto = produto_nome
        self.cargo_id = cargo_id

    @discord.ui.button(label="Comprar", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = db["config"]

        if not cfg["cargo_owner"] or not cfg["cat_suporte"]:
            return await interaction.response.send_message("❌ Bot não configurado.", ephemeral=True)

        guild = interaction.guild
        categoria = guild.get_channel(cfg["cat_suporte"])

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.get_role(cfg["cargo_owner"]): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        canal = await guild.create_text_channel(
            name=f"🛒-{interaction.user.name}",
            category=categoria,
            overwrites=overwrites
        )

        dados = db["produtos"][self.produto]
        embed = discord.Embed(title="💳 Checkout de Pagamento", color=discord.Color.blue())
        embed.add_field(name="📦 Produto", value=self.produto, inline=True)
        embed.add_field(name="💰 Valor", value=f"R$ {dados['preco']}", inline=True)
        embed.add_field(name="🔑 PIX", value=f"`{cfg['pix']}`", inline=False)
        
        if dados.get("imagem"):
            embed.set_thumbnail(url=dados["imagem"])

        await canal.send(
            content=interaction.user.mention,
            embed=embed,
            view=AdminActions(interaction.user.id, self.produto, self.cargo_id)
        )

        # Resposta com o botão de redirecionamento
        await interaction.response.send_message(
            f"✅ Carrinho criado {interaction.user.name}",
            view=RedirectView(canal.jump_url),
            ephemeral=True
        )

# ================== MODAL PRODUTO ==================
class ProdutoModal(discord.ui.Modal, title="Criar Produto"):
    nome = discord.ui.TextInput(label="Nome do Produto")
    desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph)
    preco = discord.ui.TextInput(label="Preço (Ex: 10,00)")
    estoque = discord.ui.TextInput(label="Estoque")
    imagem = discord.ui.TextInput(label="Link da Imagem (Opcional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        db["produtos"][self.nome.value] = {
            "desc": self.desc.value,
            "preco": self.preco.value,
            "estoque": self.estoque.value,
            "imagem": self.imagem.value if self.imagem.value else None
        }
        save_db(db)
        await interaction.response.send_message("✅ Produto salvo no banco!", ephemeral=True)

# ================== COMANDOS ==================
@bot.tree.command(name="setup", description="Configura as informações básicas do bot")
async def setup(interaction: discord.Interaction, pix: str, cargo_admin: discord.Role, categoria: discord.CategoryChannel):
    db["config"]["pix"] = pix
    db["config"]["cargo_owner"] = cargo_admin.id
    db["config"]["cat_suporte"] = categoria.id
    save_db(db)
    await interaction.response.send_message("✅ Configuração salva!", ephemeral=True)

@bot.tree.command(name="produtor", description="Cria um novo produto no banco de dados")
async def produtor(interaction: discord.Interaction):
    await interaction.response.send_modal(ProdutoModal())

@bot.tree.command(name="addprodutor", description="Posta o anúncio de um produto")
async def addprodutor(interaction: discord.Interaction, nome_do_produto: str, canal: discord.TextChannel, cargo: discord.Role):
    if nome_do_produto not in db["produtos"]:
        return await interaction.response.send_message("❌ Produto não encontrado no banco.", ephemeral=True)

    dados = db["produtos"][nome_do_produto]
    embed = discord.Embed(
        title="🛒 Produto Disponível",
        description=dados["desc"],
        color=discord.Color.green()
    )
    embed.add_field(name="📦 Produto", value=nome_do_produto, inline=True)
    embed.add_field(name="🛒 Estoque", value=dados["estoque"], inline=True)
    embed.add_field(name="💰 Preço", value=f"R$ {dados['preco']}", inline=True)
    
    if dados.get("imagem"):
        embed.set_image(url=dados["imagem"])

    await canal.send(embed=embed, view=BuyView(nome_do_produto, cargo.id))
    await interaction.response.send_message("✅ Anúncio postado!", ephemeral=True)

# ================== RUN ==================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
